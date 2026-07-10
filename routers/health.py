"""健康检查路由"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, Any, Optional
from database.mongodb import mongodb
from database.qdrant_client import qdrant_client
from services.document_task_dispatcher import check_document_task_queue_health
from utils.logger import logger
from utils.monitoring import performance_monitor
import psutil
import os

router = APIRouter()


class HealthStatus(BaseModel):
    """健康状态模型"""
    status: str
    version: str
    services: Dict[str, Any]
    system: Optional[Dict[str, Any]] = None


class ProbeStatusResponse(BaseModel):
    """Liveness/readiness probe response."""
    status: str
    error: Optional[str] = None
    services: Optional[Dict[str, Any]] = None


class MetricsResponse(BaseModel):
    """Runtime metrics response."""
    request_stats: Optional[Dict[str, Any]] = None
    system_metrics: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


@router.get("/health", response_model=HealthStatus)
async def health_check():
    """
    健康检查端点
    检查所有服务的连接状态
    """
    services_status = {}
    overall_status = "healthy"
    
    # MongoDB健康检查
    try:
        collection = mongodb.get_collection("documents")
        await collection.find_one({}, limit=1)
        services_status["mongodb"] = {
            "status": "healthy",
            "connected": True
        }
    except Exception as e:
        logger.warning(f"MongoDB健康检查失败: {str(e)}")
        services_status["mongodb"] = {
            "status": "unhealthy",
            "connected": False,
            "error": str(e)[:100]
        }
        overall_status = "degraded"
    
    # Qdrant健康检查
    try:
        is_healthy = qdrant_client.check_health()
        services_status["qdrant"] = {
            "status": "healthy" if is_healthy else "unhealthy",
            "connected": is_healthy
        }
        if not is_healthy:
            overall_status = "degraded"
    except Exception as e:
        logger.warning(f"Qdrant健康检查失败: {str(e)}")
        services_status["qdrant"] = {
            "status": "unhealthy",
            "connected": False,
            "error": str(e)[:100]
        }
        overall_status = "degraded"
    
    # 系统资源信息（可选）
    task_queue_status = check_document_task_queue_health()
    services_status["task_queue"] = task_queue_status
    if task_queue_status.get("status") != "healthy":
        overall_status = "degraded"

    system_info = None
    try:
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        system_info = {
            "cpu_percent": round(cpu_percent, 2),
            "memory_percent": round(memory.percent, 2),
            "memory_available_mb": round(memory.available / 1024 / 1024, 2),
            "memory_total_mb": round(memory.total / 1024 / 1024, 2),
        }
    except Exception as e:
        logger.debug(f"获取系统资源信息失败: {str(e)}")
        # 系统信息获取失败不影响健康检查
    
    return HealthStatus(
        status=overall_status,
        version="v0.8.5",
        services=services_status,
        system=system_info
    )


@router.get("/health/liveness", response_model=ProbeStatusResponse)
async def liveness_check():
    """
    Kubernetes存活探针
    简单的存活检查，不检查依赖服务
    """
    return {"status": "alive"}


@router.get("/health/readiness", response_model=ProbeStatusResponse)
async def readiness_check():
    """
    Kubernetes就绪探针
    检查关键服务是否就绪
    """
    try:
        # 检查MongoDB
        collection = mongodb.get_collection("documents")
        await collection.find_one({}, limit=1)
        
        # 如果所有关键服务都正常，返回就绪
        task_queue_status = check_document_task_queue_health()
        if (
            task_queue_status.get("active_backend") == "celery"
            and task_queue_status.get("status") != "healthy"
        ):
            return {
                "status": "not_ready",
                "error": task_queue_status.get("error") or "Celery task queue is not ready",
                "services": {"task_queue": task_queue_status},
            }

        return {"status": "ready", "services": {"task_queue": task_queue_status}}
    except Exception as e:
        logger.warning(f"就绪检查失败: {str(e)}")
        return {"status": "not_ready", "error": str(e)[:100]}


@router.get("/health/metrics", response_model=MetricsResponse)
async def metrics():
    """
    性能指标端点
    返回请求统计和系统资源使用情况
    """
    try:
        request_stats = await performance_monitor.get_stats()
        system_metrics = await performance_monitor.get_system_metrics()
        
        return {
            "request_stats": request_stats,
            "system_metrics": system_metrics
        }
    except Exception as e:
        logger.error(f"获取性能指标失败: {str(e)}", exc_info=True)
        return {"error": str(e)}

