Set WshShell = CreateObject("WScript.Shell")

' Run docker-compose silently
WshShell.Run "cmd /c docker-compose up -d", 0, True

' Run backend silently
WshShell.Run "cmd /c cd backend && call .venv\Scripts\activate.bat && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000", 0, False

' Run frontend silently
WshShell.Run "cmd /c cd frontend && npm run dev", 0, False

MsgBox "The Law Digital Human backend and frontend have started silently in the background." & vbCrLf & vbCrLf & "You can access the web interface at http://localhost:5173", 64, "Startup Successful"
