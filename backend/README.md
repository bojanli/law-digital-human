# Backend Environment Recovery

If `backend/.venv` was created with an old Python path and can no longer start, rebuild it with:

```powershell
powershell -ExecutionPolicy Bypass -File backend/scripts/rebuild_venv.ps1
```

If you want to specify another Python executable:

```powershell
powershell -ExecutionPolicy Bypass -File backend/scripts/rebuild_venv.ps1 -PythonExe C:\ProgramData\miniconda3\python.exe
```

After rebuilding:

```powershell
backend\.venv\Scripts\python.exe -m pytest
backend\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
