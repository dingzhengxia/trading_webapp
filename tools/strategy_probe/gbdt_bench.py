"""GBDT 资源占用基准：用真实数据规模（2 万行 × 25 特征）测训练/推理/内存/模型体积。"""
import os, time, tracemalloc
import numpy as np
import lightgbm as lgb
from sklearn.linear_model import LogisticRegression

N, K = 20000, 25          # 偏保守：实际 4h 方向性信号 7656 条，1h+4h 全量 25782 条
rng = np.random.default_rng(42)
X = rng.normal(size=(N, K)).astype(np.float32)
y = (X[:, 0] * 0.3 + X[:, 1] * 0.2 + rng.normal(size=N) > 0).astype(int)
print(f'数据: {N} 行 × {K} 特征 = {X.nbytes/1024/1024:.2f} MB\n')

def fit_once(n_jobs, label):
    m = lgb.LGBMClassifier(n_estimators=300, max_depth=3, num_leaves=8,
                           learning_rate=0.03, verbose=-1, n_jobs=n_jobs)
    t0 = time.perf_counter(); m.fit(X, y); dt = time.perf_counter() - t0
    print(f'训练 {label:<12} {dt*1000:>7.0f} ms')
    return m

m1 = fit_once(1, '单核')
m2 = fit_once(-1, '全核')

# 内存峰值
tracemalloc.start()
lgb.LGBMClassifier(n_estimators=300, max_depth=3, num_leaves=8, verbose=-1).fit(X, y)
cur, peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
print(f'\n训练内存峰值      {peak/1024/1024:>7.1f} MB（含数据本身 {X.nbytes/1024/1024:.2f} MB）')

# 模型体积
m1.booster_.save_model('_tmp_model.txt')
print(f'模型文件          {os.path.getsize("_tmp_model.txt")/1024:>7.1f} KB')
print(f'模型叶子节点总数  {sum(m1.booster_.trees_to_dataframe().groupby("tree_index").size()):>7d} 个')
os.remove('_tmp_model.txt')

# 推理延迟
x1, xb = X[:1], X[:30]
for _ in range(50): m1.predict_proba(x1)
t0 = time.perf_counter()
for _ in range(5000): m1.predict_proba(x1)
one = (time.perf_counter() - t0) / 5000 * 1000
t0 = time.perf_counter()
for _ in range(500): m1.predict_proba(xb)
batch = (time.perf_counter() - t0) / 500 * 1000
print(f'\n单条推理          {one:>7.3f} ms')
print(f'批量 30 条        {batch:>7.3f} ms  （一次扫描全部币）')

# 对照：逻辑回归
lr = LogisticRegression(max_iter=1000)
t0 = time.perf_counter(); lr.fit(X, y); tlr = time.perf_counter() - t0
t0 = time.perf_counter()
for _ in range(5000): lr.predict_proba(x1)
lone = (time.perf_counter() - t0) / 5000 * 1000
print(f'\n对照 逻辑回归     训练 {tlr*1000:.0f} ms / 推理 {lone:.3f} ms / 参数 {lr.coef_.size} 个（{~lr.coef_.size*8/1024:.1f} KB）')
