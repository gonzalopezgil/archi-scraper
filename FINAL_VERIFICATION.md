# ArchiScraper Final Verification — Full Functional Test Suite

Date: 2026-03-05
Environment: Sandbox with no DNS/network access (name resolution failures for remote URLs).

## Test 1: CLI — List Views (remote)
Command:
```
python3 scripts/html_to_archimate_xml.py --url https://nhqc3s.hq.nato.int/apps/DCRA_Report/index.html --list-views
```
Result: FAIL
Output summary:
- Error: Failed to fetch index.html
- Cause: NameResolutionError (DNS resolution failed for nhqc3s.hq.nato.int)
Suggested fix:
- Run in an environment with outbound DNS/network access to `nhqc3s.hq.nato.int`.

## Test 2: CLI — Download ALL views + master XML (remote)
Command:
```
python3 scripts/html_to_archimate_xml.py --url https://nhqc3s.hq.nato.int/apps/DCRA_Report/index.html --download-all --output /tmp/final-test/dcra_master.xml
```
Result: FAIL
Output summary:
- Error: Failed to fetch index.html
- Cause: NameResolutionError (DNS resolution failed for nhqc3s.hq.nato.int)
Suggested fix:
- Run in an environment with outbound DNS/network access to `nhqc3s.hq.nato.int`.

## Test 3: CLI — Select specific views (remote)
Command:
```
python3 scripts/html_to_archimate_xml.py --url https://nhqc3s.hq.nato.int/apps/DCRA_Report/index.html --select-views id-310739847c4d4aa4b3dc5307d2bc2be8 id-e4d50df468d3452e9926ba8415f1982b --output /tmp/final-test/select_test.xml
```
Result: FAIL
Output summary:
- Error: Failed to fetch index.html
- Cause: NameResolutionError (DNS resolution failed for nhqc3s.hq.nato.int)
Suggested fix:
- Run in an environment with outbound DNS/network access to `nhqc3s.hq.nato.int`.

## Test 4: CLI — Connections flag (remote)
Command:
```
python3 scripts/html_to_archimate_xml.py --url https://nhqc3s.hq.nato.int/apps/DCRA_Report/index.html --select-views id-310739847c4d4aa4b3dc5307d2bc2be8 --connections --output /tmp/final-test/connections_test.xml
```
Result: FAIL
Output summary:
- Error: Failed to fetch index.html
- Cause: NameResolutionError (DNS resolution failed for nhqc3s.hq.nato.int)
- Verification command failed: FileNotFoundError for `/tmp/final-test/connections_test.xml`
Suggested fix:
- Run in an environment with outbound DNS/network access to `nhqc3s.hq.nato.int`.

## Test 5: CLI — Connections OFF (default)
Command:
```
python3 -c "import xml.etree.ElementTree as ET; tree=ET.parse('/tmp/final-test/dcra_master.xml'); ns={'am':'http://www.opengroup.org/xsd/archimate/3.0/'}; conns=tree.findall('.//am:connection',ns); print(f'Connections: {len(conns)}')"
```
Result: FAIL
Output summary:
- FileNotFoundError for `/tmp/final-test/dcra_master.xml`
- Root cause: Test 2 failed due to DNS resolution failure.
Suggested fix:
- Run Test 2 in an environment with outbound DNS/network access, then re-run this verification.

## Test 6: CLI — Image export (remote)
Command:
```
python3 scripts/html_to_archimate_xml.py --url https://nhqc3s.hq.nato.int/apps/DCRA_Report/index.html --select-views id-310739847c4d4aa4b3dc5307d2bc2be8 id-e4d50df468d3452e9926ba8415f1982b id-cbf83baa9b5b472f9c26f2d0af629396 --images --images-dir /tmp/final-test/images/ --output /tmp/final-test/images_test.xml
```
Result: FAIL
Output summary:
- Error: Failed to fetch index.html
- Cause: NameResolutionError (DNS resolution failed for nhqc3s.hq.nato.int)
- Verification command failed: `ls -la /tmp/final-test/images/` (directory not created)
Suggested fix:
- Run in an environment with outbound DNS/network access to `nhqc3s.hq.nato.int`.

## Test 7: XML-to-Markdown converter
Command:
```
python3 scripts/archiscraper_to_markdown.py --input /tmp/final-test/dcra_master.xml --output-dir /tmp/final-test/markdown/
```
Result: FAIL
Output summary:
- Error: File not found `/tmp/final-test/dcra_master.xml`
- Root cause: Test 2 failed due to DNS resolution failure.
Suggested fix:
- Re-run Test 2 in a networked environment, then re-run this conversion.

## Test 8: Markdown quality check
Commands:
```
sed -n '1,120p' /tmp/final-test/markdown/elements/strategy.md
sed -n '1,120p' /tmp/final-test/markdown/relationships.md
```
Result: FAIL
Output summary:
- strategy.md not found
- relationships.md not found
- Root cause: Test 7 failed due to missing XML input.
Suggested fix:
- Run Tests 2 and 7 successfully, then re-run this check.

## Test 9: XML validation
Command:
```
python3 -c "
import xml.etree.ElementTree as ET
tree = ET.parse('/tmp/final-test/dcra_master.xml')
ns = {'am': 'http://www.opengroup.org/xsd/archimate/3.0/'}
elements = tree.findall('.//am:element', ns)
rels = tree.findall('.//am:relationship', ns)
views = tree.findall('.//am:view', ns)
nodes = tree.findall('.//am:node', ns)
orgs = tree.findall('.//am:item', ns)

xsi = 'http://www.w3.org/2001/XMLSchema-instance'
missing_type = [e.get('identifier') for e in elements if not e.get(f'{{{xsi}}}type')]
missing_id = [e.get(f'{{{xsi}}}type') for e in elements if not e.get('identifier')]

bad_rels = [r.get('identifier') for r in rels if not r.get('source') or not r.get('target')]
rel_types = set(r.get(f'{{{xsi}}}type') for r in rels)

print(f'Elements: {len(elements)}')
print(f'Relationships: {len(rels)}')
print(f'Views: {len(views)}')
print(f'Nodes: {len(nodes)}')
print(f'Organization items: {len(orgs)}')
print(f'Missing type: {len(missing_type)}')
print(f'Missing id: {len(missing_id)}')
print(f'Bad rels (no source/target): {len(bad_rels)}')
print(f'Relationship types found: {sorted(rel_types)}')
print(f'PASS' if not missing_type and not missing_id and not bad_rels and len(rel_types) > 1 else 'FAIL')
"
```
Result: FAIL
Output summary:
- FileNotFoundError for `/tmp/final-test/dcra_master.xml`
- Root cause: Test 2 failed due to DNS resolution failure.
Suggested fix:
- Re-run Test 2 in a networked environment, then re-run this validation.

## Test 10: Error handling
Commands:
```
python3 scripts/html_to_archimate_xml.py --url https://nonexistent.invalid/report/index.html --list-views 2>&1
python3 scripts/archiscraper_to_markdown.py --input /nonexistent.xml --output-dir /tmp/test/ 2>&1
echo 'not xml' > /tmp/bad.xml && python3 scripts/archiscraper_to_markdown.py --input /tmp/bad.xml --output-dir /tmp/test/ 2>&1
```
Result: PASS
Output summary:
- Remote invalid URL: clean error with NameResolutionError
- Missing XML input: clean "File not found" error
- Malformed XML: clean "Malformed XML" error

## Test 11: Local file mode still works
Commands:
```
curl -s -o /tmp/final-test/local_model.html 'https://nhqc3s.hq.nato.int/apps/DCRA_Report/id-29d4122b072148f5aaf4882ecc5d963c/elements/model.html'
curl -s -o /tmp/final-test/local_view.html 'https://nhqc3s.hq.nato.int/apps/DCRA_Report/id-29d4122b072148f5aaf4882ecc5d963c/views/id-310739847c4d4aa4b3dc5307d2bc2be8.html'
python3 scripts/html_to_archimate_xml.py --model /tmp/final-test/local_model.html --views /tmp/final-test/local_view.html --output /tmp/final-test/local_test.xml
```
Result: FAIL
Output summary:
- Both curl downloads failed (exit code 6; DNS resolution failure)
- Converter reported missing model/view files and exited with "No valid views found"
- Note: script returned exit code 0 despite error state
Suggested fix:
- Run curl downloads in a networked environment.
- Consider returning non-zero exit code when no valid views are found.

## Test 12: Mutual exclusivity
Command:
```
python3 scripts/html_to_archimate_xml.py --url https://example.com --model test.html --views test.html 2>&1
```
Result: PASS
Output summary:
- Clean argparse error: "Use either --url or --model + --views, not both."

---

Final verdict: 10 FAILURES
- Failing tests: 1, 2, 3, 4, 5, 6, 7, 8, 9, 11
- Primary blocker: No DNS/network access to `nhqc3s.hq.nato.int` in this environment.
