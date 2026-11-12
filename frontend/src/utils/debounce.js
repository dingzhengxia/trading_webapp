// frontend/src/utils/debounce.ts
// 本地 debounce 实现，替代原先的第三方 debounce 工具（无网络环境不新增依赖）。
/**
 * 创建一个防抖函数：在最后一次调用后 wait 毫秒才执行。
 * @param fn 需要防抖的函数
 * @param wait 等待毫秒数，默认 0
 */
export function debounce(fn, wait = 0) {
    let timer;
    let pendingArgs = null;
    const invoke = () => {
        timer = undefined;
        if (pendingArgs === null)
            return undefined;
        const args = pendingArgs;
        pendingArgs = null;
        return fn(...args);
    };
    const debounced = ((...args) => {
        pendingArgs = args;
        if (timer !== undefined) {
            clearTimeout(timer);
        }
        timer = setTimeout(invoke, wait);
    });
    debounced.cancel = () => {
        if (timer !== undefined) {
            clearTimeout(timer);
            timer = undefined;
        }
        pendingArgs = null;
    };
    debounced.flush = () => {
        if (timer === undefined)
            return;
        clearTimeout(timer);
        invoke();
    };
    return debounced;
}
