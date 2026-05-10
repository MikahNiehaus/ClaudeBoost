@echo off
setlocal enabledelayedexpansion

echo.
echo  ClaudeBoost Installer
echo  =====================
echo.
echo  This installs ClaudeBoost extensions globally so every project
echo  has access to agents, knowledge bases, RAG search, and slash commands.
echo.

:: Get the directory where this script lives (ClaudeBoost root)
set "BOOST_DIR=%~dp0"
set "BOOST_DIR=%BOOST_DIR:~0,-1%"

:: Target directories
set "CLAUDE_DIR=%USERPROFILE%\.claude"
set "GT_DIR=%USERPROFILE%\gt"

echo  Source:  %BOOST_DIR%
echo  Target:  %CLAUDE_DIR%
echo.

:: ============================================================
:: 1. Register RAG MCP server globally
:: ============================================================
echo  [1/4] Registering RAG MCP server...

python -c "import rag_server" >nul 2>&1
if errorlevel 1 (
    echo         Installing rag-server package...
    call pip install -e "%BOOST_DIR%\mcp-rag-server" >nul 2>&1
    if errorlevel 1 (
        echo         WARNING: Could not install rag-server. Install manually:
        echo           pip install -e "%BOOST_DIR%\mcp-rag-server"
    ) else (
        echo         rag-server package installed.
    )
) else (
    echo         rag-server already installed.
)

where claude >nul 2>&1
if not errorlevel 1 (
    call claude mcp remove rag-server --scope user >nul 2>&1
    call claude mcp add rag-server --scope user -e RAG_PROJECT_ROOT="%BOOST_DIR%" -- python -m rag_server >nul 2>&1
    echo         MCP server registered globally (RAG_PROJECT_ROOT=%BOOST_DIR%).
) else (
    echo         Claude CLI not found. Add manually to ~/.claude.json:
    echo           "mcpServers": { "rag-server": { "command": "python", "args": ["-m", "rag_server"], "env": { "RAG_PROJECT_ROOT": "%BOOST_DIR%" } } }
)

:: ============================================================
:: 2. Copy slash commands globally
:: ============================================================
:: Hardlink CLAUDE.md globally (same file, auto-updates)
if exist "%CLAUDE_DIR%\CLAUDE.md" del "%CLAUDE_DIR%\CLAUDE.md" >nul 2>&1
mklink /h "%CLAUDE_DIR%\CLAUDE.md" "%BOOST_DIR%\CLAUDE.md" >nul 2>&1
echo         CLAUDE.md linked to %CLAUDE_DIR%\CLAUDE.md (auto-updates).

echo  [2/4] Installing slash commands...

:: Junction commands folder (reads directly from ClaudeBoost, auto-updates)
if exist "%CLAUDE_DIR%\commands" (
    rmdir /s /q "%CLAUDE_DIR%\commands" >nul 2>&1
    rmdir "%CLAUDE_DIR%\commands" >nul 2>&1
)
if not exist "%CLAUDE_DIR%\commands" (
    mklink /j "%CLAUDE_DIR%\commands" "%BOOST_DIR%\.claude\commands" >nul 2>&1
)
echo         Slash commands linked.

:: ============================================================
:: 3. Copy agents and knowledge to GT directives (if GT installed)
:: ============================================================
echo  [3/4] Setting up GT directives...

if exist "%GT_DIR%" (
    :: Remove old copies if they exist
    if exist "%GT_DIR%\directives\agents" (
        rmdir /s /q "%GT_DIR%\directives\agents" >nul 2>&1
        rmdir "%GT_DIR%\directives\agents" >nul 2>&1
    )
    if exist "%GT_DIR%\directives\knowledge" (
        rmdir /s /q "%GT_DIR%\directives\knowledge" >nul 2>&1
        rmdir "%GT_DIR%\directives\knowledge" >nul 2>&1
    )

    :: Create junctions so GT reads directly from ClaudeBoost (auto-updates)
    mklink /j "%GT_DIR%\directives\agents" "%BOOST_DIR%\agents" >nul 2>&1
    mklink /j "%GT_DIR%\directives\knowledge" "%BOOST_DIR%\knowledge" >nul 2>&1
    echo         Agents and knowledge linked to GT directives (auto-updates).
) else (
    echo         GT not installed. Skipping GT directives.
    echo         Agents and knowledge are still available locally in ClaudeBoost.
)

:: ============================================================
:: 4. Initial RAG index
:: ============================================================
echo  [4/4] Building initial RAG index...

set "RAG_PROJECT_ROOT=%BOOST_DIR%"
python -c "from rag_server.core.embedding import SentenceTransformerEmbedding; from rag_server.core.store import ChromaStore; from rag_server.indexing.engine import IndexingEngine; from rag_server.config import CHROMA_DIR; e=SentenceTransformerEmbedding(); s=ChromaStore(str(CHROMA_DIR)); eng=IndexingEngine(e,s); r=eng.index_all(force=True); print(f'Indexed {r[\"files_indexed\"]} files, {r[\"chunks_created\"]} chunks')" 2>&1
if errorlevel 1 (
    echo         Skipped. Run rag_index from Claude Code to index later.
) else (
    echo         Index built successfully.
)

:: Count slash commands for summary
set CMD_COUNT=0
for /f %%i in ('dir /b /a-d "%BOOST_DIR%\.claude\commands\*.md" 2^>nul ^| find /c /v ""') do set CMD_COUNT=%%i

echo.
echo  ============================================================
echo   ClaudeBoost installed!
echo.
echo   What's available now:
echo     - RAG search in every Claude Code session
echo     - !CMD_COUNT! slash commands (global)
if exist "%GT_DIR%" (
    echo     - Agents and knowledge in GT directives
)
echo.
echo   To verify: open any project in Claude Code and try:
echo     rag_status
echo  ============================================================
echo.

endlocal\r
