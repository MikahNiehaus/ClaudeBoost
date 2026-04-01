# Browser Testing with Playwright MCP

<knowledge-base name="playwright" version="1.0">
<triggers>browser, playwright, interactive, e2e, end-to-end, click, navigate, test app, manual test</triggers>
<overview>Interactive browser testing using Playwright MCP tools. ALWAYS use MCP tools for browser requests unless user explicitly asks for test scripts.</overview>

<critical-default-behavior>
  <rule>ALWAYS use interactive mode (MCP tools) for ANY browser/Playwright request</rule>
  <use-mcp>"Open google", "Test my app", "Click the button", "Check the login flow"</use-mcp>
  <only-write-code>"Write a Playwright test", "Generate test automation"</only-write-code>
  <when-in-doubt>USE MCP TOOLS, NOT CODE</when-in-doubt>
</critical-default-behavior>

<known-failures>
  <failure name="Wrong Package Name">
    <wrong>@anthropic-ai/mcp-playwright (does not exist)</wrong>
    <correct>@playwright/mcp (Microsoft official)</correct>
  </failure>
  <failure name="Restart Required">
    <note>MCP servers load at Claude Code startup. MUST restart after installation.</note>
  </failure>
  <failure name="Health Check Required">
    <command>claude mcp list</command>
    <success>playwright: npx @playwright/mcp@latest - ✓ Connected</success>
    <failure>✗ Failed to connect</failure>
  </failure>
</known-failures>

<mcp-setup>
  <install>claude mcp add playwright -- npx @playwright/mcp@latest</install>
  <with-headless>--headless</with-headless>
  <with-browser>--browser chromium|firefox|webkit</with-browser>
  <with-device>--device "iPhone 15"</with-device>
  <with-persistent-data>--user-data-dir ./browser-data</with-persistent-data>
  <with-viewport>--viewport-size 1920x1080</with-viewport>
  <verify>claude mcp list</verify>
  <restart-required>Yes - MCP servers load at startup</restart-required>
</mcp-setup>

<cli-options>
  <option name="--browser" desc="Browser type">chromium, firefox, webkit, msedge</option>
  <option name="--headless" desc="Run without visible window"/>
  <option name="--viewport-size" desc="Window dimensions">1280x720</option>
  <option name="--device" desc="Emulate device">"iPhone 15"</option>
  <option name="--user-data-dir" desc="Persistent browser profile">./data</option>
  <option name="--storage-state" desc="Load cookies/storage from JSON">auth.json</option>
  <option name="--isolated" desc="Fresh profile each session"/>
  <option name="--timeout-action" desc="Action timeout ms">5000</option>
  <option name="--timeout-navigation" desc="Navigation timeout ms">60000</option>
  <option name="--proxy-server" desc="Use proxy">http://proxy:3128</option>
  <option name="--save-video" desc="Record session">800x600</option>
  <option name="--save-trace" desc="Save Playwright trace"/>
</cli-options>

<url-access-policy>
  <auto-allow>localhost:*, 127.0.0.1:*, *.localhost, [::1]</auto-allow>
  <auto-allow-oauth>
    *.b2clogin.com, login.microsoftonline.com, login.live.com,
    accounts.google.com, *.auth0.com, *.okta.com, *.oktapreview.com,
    github.com/login/oauth, *.auth.*.amazoncognito.com, *.firebaseapp.com
  </auto-allow-oauth>
  <ask-user>Other external URLs</ask-user>
</url-access-policy>

<essential-tools>
  <tool name="browser_navigate">Go to URL - Start of any test flow</tool>
  <tool name="browser_snapshot">Get page state as accessibility tree - Before clicking</tool>
  <tool name="browser_click">Click element - Buttons, links, form controls</tool>
  <tool name="browser_type">Enter text - Form inputs, search boxes</tool>
  <tool name="browser_take_screenshot">Visual capture - Document findings</tool>
  <tool name="browser_close">End session - When done testing</tool>
  <tool name="browser_fill_form">Fill multiple fields at once - Complex forms</tool>
  <tool name="browser_select_option">Select dropdown option</tool>
  <tool name="browser_hover">Hover over element - Tooltips, dropdowns</tool>
  <tool name="browser_press_key">Press keyboard key - Enter, Escape, Tab</tool>
  <tool name="browser_wait_for">Wait for text/element - Dynamic content</tool>
</essential-tools>

<troubleshooting>
  <problem name="Wrong package">
    <solution>claude mcp remove playwright &amp;&amp; claude mcp add playwright -- npx @playwright/mcp@latest</solution>
  </problem>
  <problem name="Tools not appearing">
    <solution>Restart Claude Code - MCP servers load at startup</solution>
  </problem>
  <problem name="Server fails to connect">
    <solution>node --version (need 18+), npx playwright install</solution>
  </problem>
  <problem name="Can't find elements">
    <solution>Always browser_snapshot first - shows elements with [ref=...] IDs</solution>
  </problem>
</troubleshooting>

<session-lifecycle>
  <start>
    <step>Verify MCP installed and connected</step>
    <step>Use browser_navigate to open URL</step>
    <step>Use browser_snapshot to see page state</step>
  </start>
  <during>
    <note>Snapshots show elements with [ref=eXX] identifiers</note>
    <note>Use refs for clicking: ref="e42"</note>
    <note>Take screenshots to document findings</note>
  </during>
  <end>
    <step>Use browser_close to close browser cleanly</step>
    <step>Report summary of what was tested</step>
  </end>
</session-lifecycle>

<quick-reference><![CDATA[
INSTALL:   claude mcp add playwright -- npx @playwright/mcp@latest
VERIFY:    claude mcp list
RESTART:   Required after install!
PACKAGE:   @playwright/mcp (Microsoft official)
NOT:       @anthropic-ai/mcp-playwright (doesn't exist)
DEFAULT:   ALWAYS use MCP tools interactively
EXCEPTION: Only write code if user explicitly asks
]]></quick-reference>

</knowledge-base>
