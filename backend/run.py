import uvicorn

if __name__ == "__main__":
    # ★ SQLite + 进程内 WS 管理器 + task_queue worker：必须单进程单 worker
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, workers=1, reload=False)
