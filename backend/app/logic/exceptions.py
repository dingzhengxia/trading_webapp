
class RetriableOrderError(Exception):
    """可重试的订单错误"""
    pass

class TaskInterruptedError(Exception):
    """任务被用户中断的错误。

    注意：不得使用内置异常名 InterruptedError 作为业务异常类名——
    那会遮蔽内建类型并让 except 分支难以区分（T13 / P2-5）。
    """
    pass
