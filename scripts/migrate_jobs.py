"""
任务迁移脚本

用于在项目重构后迁移旧任务数据

用法:
  python scripts/migrate_jobs.py export   # 导出任务配置
  python scripts/migrate_jobs.py import   # 导入任务配置
"""
import json
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def export_jobs(output_file="jobs_backup.json"):
    """导出当前任务配置"""
    from app.services.scheduler import scheduler
    from app.services.tasks import get_task_info
    
    try:
        jobs = scheduler.get_jobs()
    except Exception as e:
        print(f"获取任务失败: {e}")
        return
    
    job_configs = []
    for job in jobs:
        try:
            config = {
                "id": job.id,
                "name": job.name,
                "func": job.func.__name__,
                "args": list(job.args) if job.args else [],
                "kwargs": dict(job.kwargs) if job.kwargs else {},
                "trigger_type": None,
                "trigger_args": {},
                "next_run_time": str(job.next_run_time) if job.next_run_time else None,
                "paused": job.next_run_time is None
            }
            
            trigger_str = str(job.trigger)
            if "interval" in trigger_str:
                config["trigger_type"] = "interval"
            elif "cron" in trigger_str:
                config["trigger_type"] = "cron"
            elif "date" in trigger_str:
                config["trigger_type"] = "date"
            
            job_configs.append(config)
        except Exception as e:
            print(f"导出任务 {job.id} 失败: {e}")
    
    output_path = Path(output_file)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(job_configs, f, indent=2, ensure_ascii=False)
    
    print(f"已导出 {len(job_configs)} 个任务到 {output_path}")
    return job_configs


def import_jobs(input_file="jobs_backup.json"):
    """导入任务配置"""
    from app.services.scheduler import scheduler, add_job, pause_job
    from app.services.tasks import get_task
    
    input_path = Path(input_file)
    if not input_path.exists():
        print(f"文件不存在: {input_path}")
        return
    
    with open(input_path, "r", encoding="utf-8") as f:
        job_configs = json.load(f)
    
    imported = 0
    for config in job_configs:
        try:
            if scheduler.get_job(config["id"]):
                print(f"任务 {config['id']} 已存在，跳过")
                continue
            
            task_func = get_task(config["func"])
            if not task_func:
                print(f"任务函数 {config['func']} 不存在，跳过")
                continue
            
            add_job(
                func_name=config["func"],
                trigger=config["trigger_type"],
                args=config["args"],
                kwargs=config["kwargs"],
                job_id=config["id"],
                name=config["name"]
            )
            
            if config.get("paused"):
                pause_job(config["id"])
            
            imported += 1
            print(f"已导入任务: {config['id']}")
        except Exception as e:
            print(f"导入任务 {config['id']} 失败: {e}")
    
    print(f"成功导入 {imported} 个任务")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "export":
        export_jobs()
    elif command == "import":
        import_jobs()
    else:
        print(f"未知命令: {command}")
        print(__doc__)