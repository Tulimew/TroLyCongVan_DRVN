Set WshShell = CreateObject("WScript.Shell")
scriptDir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
pythonExe = "C:\Users\tangt\AppData\Local\Programs\Python\Python312\pythonw.exe"
WshShell.CurrentDirectory = scriptDir
WshShell.Run """" & pythonExe & """ """ & scriptDir & "\main.py""", 0, False
