
class RetriableOrderError(Exception):
    """可重试的订单错误"""
    pass

class InterruptedError(Exception):
    """任务被用户中断的错误"""
    pass