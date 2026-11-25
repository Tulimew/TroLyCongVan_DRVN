Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = scriptDir

pythonExe = "pythonw.exe"
localAppData = WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%")

' Kiem tra cac thu muc cai dat Python pho bien tren Windows
Dim candidatePaths
candidatePaths = Array(_
    scriptDir & "\runtime\pythonw.exe", _
    localAppData & "\Programs\Python\Python312\pythonw.exe", _
    localAppData & "\Programs\Python\Python311\pythonw.exe", _
    localAppData & "\Programs\Python\Python310\pythonw.exe", _
    localAppData & "\Programs\Python\Python313\pythonw.exe", _
    "C:\Python312\pythonw.exe", _
    "C:\Python311\pythonw.exe", _
    "C:\Python310\pythonw.exe" _
)

Dim p
For Each p In candidatePaths
    If fso.FileExists(p) Then
        pythonExe = p
        Exit For
    End If
Next

WshShell.Run """" & pythonExe & """ """ & scriptDir & "\main.py""", 0, False
