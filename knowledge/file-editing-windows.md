# File Editing on Windows - Known Issues and Workarounds

<knowledge-base name="file-editing-windows" version="1.0">
<triggers>file edit, write file, unexpectedly modified, edit error, windows</triggers>
<overview>Critical Windows-specific bug in Claude Code causing "File has been unexpectedly modified" errors. Tracked in GitHub issues #7443, #7457, #10437, #12462, #12805.</overview>

<symptoms>
  <symptom>Edit/Write tools fail with "File has been unexpectedly modified"</symptom>
  <symptom>Error occurs even immediately after reading the file</symptom>
  <symptom>File was NOT actually modified by external process</symptom>
  <symptom>More common with absolute paths</symptom>
</symptoms>

<root-causes suspected="true">
  <cause>Windows/MINGW file system timestamp resolution differences</cause>
  <cause>Line ending conversion (CRLF vs LF) detected as modification</cause>
  <cause>File hash/tracking cache not persisting correctly</cause>
  <cause>VSCode background processes (formatters, linters, file watchers)</cause>
</root-causes>

<workarounds>
  <workaround priority="1" name="Use Relative Paths" primary="true">
    <correct>./src/file.ts, agents/_shared-output.md</correct>
    <wrong>C:/prj/ClaudeMemory/agents/_shared-output.md</wrong>
    <rule>ALWAYS use relative paths (e.g., ./src/file.ts). DO NOT use absolute paths.</rule>
  </workaround>

  <workaround priority="2" name="Retry Pattern">
    <step>Wait 1-2 seconds</step>
    <step>Read file again</step>
    <step>Attempt edit immediately after read</step>
    <step>If fails again, try next workaround</step>
  </workaround>

  <workaround priority="3" name="Use Bash Commands">
    <for-replacements>sed -i 's/old_string/new_string/g' file.txt</for-replacements>
    <for-appending><![CDATA[cat >> file.txt << 'EOF'
New content here
EOF]]></for-appending>
    <for-full-replacement><![CDATA[python -c "
content = '''Your file content here'''
with open('file.txt', 'w', encoding='utf-8') as f:
    f.write(content)
"]]></for-full-replacement>
  </workaround>

  <workaround priority="4" name="Create New File">
    <step>Create new file with different name</step>
    <step>Write full content to new file</step>
    <step>Delete old file: rm old_file.md</step>
    <step>Rename new file: mv new_file.md old_file.md</step>
  </workaround>

  <workaround priority="5" name="Restart Claude Code">
    <note>Temporarily resolves the issue but loses conversation context</note>
  </workaround>
</workarounds>

<agent-guidelines>
  <on-error>
    <step attempt="1">Try with relative path</step>
    <step attempt="2">Read file, immediately edit, don't wait</step>
    <step attempt="3">Use Bash workaround</step>
    <step attempt="all-fail">Report to user, suggest restart, offer new file alternative</step>
  </on-error>
  <preventive>
    <rule>Always use relative paths in file operations</rule>
    <rule>Don't batch multiple reads before edits</rule>
    <rule>Edit immediately after reading</rule>
    <rule>For critical files: Consider "new file + rename" pattern</rule>
  </preventive>
</agent-guidelines>

<rule id="RULE-011" name="Windows File Edit Resilience" severity="WARN">
  <trigger>When Edit/Write tool fails with "unexpectedly modified" error</trigger>
  <condition>On Windows platform</condition>
  <action>
    <step>Retry with relative path</step>
    <step>If fails, use Bash/sed workaround</step>
    <step>If fails, report to user</step>
  </action>
</rule>

</knowledge-base>
