"""优化的日志配置模块 - 支持异步日志写入"""
import logging
import os
import queue
import threading
from logging.handlers import RotatingFileHandler, QueueHandler, QueueListener
from pathlib import Path


class AsyncFileHandler(RotatingFileHandler):
    """异步文件处理器，使用队列避免阻塞主线程"""
    pass


def setup_logger(name: str = "context-engine-api", log_level: str = None) -> logging.Logger:
    """配置并返回日志记录器（支持异步写入）"""
    # 获取日志级别
    if log_level is None:
        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    
    level = getattr(logging, log_level, logging.INFO)
    
    # 创建日志记录器
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # 避免重复添加处理器
    if logger.handlers:
        return logger
    
    # 创建日志目录
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # 简化的日志格式
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # 控制台处理器（同步，用于开发调试）
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    
    # 文件处理器（异步写入，避免阻塞）
    file_handler = RotatingFileHandler(
        filename=log_dir / f"{name}.log",
        maxBytes=10 * 1024 * 1024,  # 10MB（增加文件大小）
        backupCount=5,  # 保留5个备份文件
        encoding="utf-8"
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    
    # 使用队列实现异步日志写入
    log_queue = queue.Queue(maxsize=1000)  # 队列大小限制，防止内存溢出
    
    # 创建队列监听器，在后台线程中处理日志
    queue_listener = QueueListener(log_queue, file_handler, respect_handler_level=True)
    queue_listener.start()
    
    # 添加队列处理器（异步）和控制台处理器（同步）
    queue_handler = QueueHandler(log_queue)
    logger.addHandler(queue_handler)
    logger.addHandler(console_handler)
    
    # 过滤掉一些不必要的日志
    # 减少第三方库的日志输出
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("motor").setLevel(logging.WARNING)
    logging.getLogger("pymongo").setLevel(logging.WARNING)
    
    # 在生产环境中，减少INFO级别的日志输出
    if os.getenv("ENVIRONMENT") == "production":
        # 只记录WARNING及以上级别的日志到文件
        file_handler.setLevel(logging.WARNING)
    
    return logger


# 全局日志记录器实例
logger = setup_logger()

