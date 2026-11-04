# Offline checks (no network): python3 cseec-official-admissions/test_offline.py
import importlib.util, sys
spec = importlib.util.spec_from_file_location("adm", __import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), "cseec_official_admissions.py"))
adm = importlib.util.module_from_spec(spec); spec.loader.exec_module(adm)
nav = "".join(f"<li><a href='/applying-ubc/x{i}'>Admission requirements {i}</a></li>" for i in range(80))
navpad = "<p>Canadian English admission requirement grade report 2026 overview of everything on this site menu</p>"*30
def page(body):
    p = adm.Page(); p.raw = body; p.feed(body); return p.visible_text()
# 1 nav + main with requirements
html1 = f"<html><head><title>T</title></head><body><header><nav><ul>{nav}</ul></nav>{navpad}</header><main><h1>BC applicants</h1><p>You need English Studies 12 or English First Peoples 12 with a minimum of 70%.</p><p>Science: Pre-Calculus 12, Chemistry 12 and Physics 12 or Biology 12.</p>{'<p>Other filler text about student life on campus and housing options.</p>'*10}</main><footer>{navpad}</footer></body></html>"
t = page(html1)
assert "Admission requirements 3" not in t and "Pre-Calculus 12" in t, t[:300]
ex, _ = adm.excerpts(t, ("science",), "requirements")
assert adm.has_evidence(ex, "requirements") and ex.index("English Studies 12") < 400, ex[:400]
# 2 JS-loaded page: only nav + intro text, no requirements
html2 = f"<html><body><nav><ul>{nav}</ul></nav><div id='app'><p>Select your campus, province and degree to see the admission requirements that apply to you as a Canadian applicant.</p>{'<p>Admission at UBC is competitive and considers your whole application including personal profile.</p>'*5}</div></body></html>"
t2 = page(html2)
ex2, _ = adm.excerpts(t2, (), "requirements")
assert not adm.has_evidence(ex2, "requirements"), ex2
# 3 page without semantic tags still readable
html3 = "<html><body>" + "<div><p>Applicants must present English 12 with a minimum grade of 67% and Math 12.</p></div>"*8 + "</body></html>"
assert adm.has_evidence(adm.excerpts(page(html3), (), "requirements")[0], "requirements")
# 4 deadlines / language / history
assert adm.has_evidence("Apply by January 15, 2027", "deadlines")
assert adm.has_evidence("IELTS Academic overall 6.5", "language")
assert adm.has_evidence("Admission range: 85-92% in 2025", "history")
assert not adm.has_evidence("Dates and deadlines", "deadlines")
# 5 collect status with fake fetch
class P: pass
def fake_fetch(url, inst):
    p = adm.Page(); p.raw = html2; p.feed(html2); return p, url
adm.fetch_page = fake_fetch; adm.store_result = lambda k, r: None; adm.cached_result = lambda k: None
def no_network(fields): raise OSError("offline test")
adm.ubc_post = no_network
r = adm.collect("ubc", "requirements", "science", 2027)
assert r["status"] == "no_requirement_text" and "冲刺" in r["instruction"], r["status"]
def fake_fetch2(url, inst):
    p = adm.Page(); p.raw = html1; p.feed(html1); return p, url
adm.fetch_page = fake_fetch2
r = adm.collect("sfu", "requirements", "general", 2027)
assert r["status"] == "evidence_found", r["status"]
c = adm.compact(r); assert len(c["sources"][0]["excerpt"]) <= 2500
print("all ok", len(ex), len(ex2))
# 6 "% complete" is not evidence
assert not adm.has_evidence("please arrange for interim (50% complete) grades to be sent", "requirements")
# 7 UBC service
calls = []
def fake_post(fields):
    calls.append(fields)
    if fields["action"] == "requirements_load_programs":
        return {"result": True, "programs": {"530014": "Science", "438208": "Arts"},
                "general": "<ul><li>Graduation from high school</li><li>Minimum of 70% in Grade 11 or Grade 12 English (or their equivalents)</li></ul>",
                "english": "<p>English language competency</p>"}
    assert fields["requirement"] == "530014"
    return {"result": True, "specific": "<div class='results'><h3>Science</h3><h5>Grade 12 requirements</h5><ul><li>English Studies 12 or English First Peoples 12</li><li>Pre-Calculus 12</li><li>Anatomy and Physiology 12, or Chemistry 12, or Physics 12</li></ul></div>"}
adm.ubc_post = fake_post
seen = []
adm.fetch_page = lambda url, inst: seen.append(url) or fake_fetch(url, inst)
r = adm.collect("ubc", "requirements", "computing", 2027)
assert r["status"] == "evidence_found" and not seen, (r["status"], seen)
src = r["sources"][0]; assert "Pre-Calculus 12" in src["excerpt"] and "Computer Science" in src["note"], src
# UBC service down -> falls back to the static page and is not marked as found
def broken(fields): raise TimeoutError()
adm.ubc_post = broken
r = adm.collect("ubc", "requirements", "science", 2027)
assert r["status"] == "no_requirement_text" and r["failures"] and seen, r["status"]
# 8 SFU science page is read
seen.clear()
r = adm.collect("sfu", "requirements", "science", 2027)
assert any(u.endswith("/bc-yukon/science.html") for u in seen), seen
# 9 program link choice: other directions are skipped, "science" alone never excludes
links_html = "<html><body><main>" + "<p>Admission requirements for BC and Yukon applicants: English 12 with a minimum of 70%.</p>"*6 + "".join(
    f"<p><a href='https://www.sfu.ca/students/admission/admission-requirements/canadian-highschool/bc-yukon/{n}.html'>{n}</a></p>"
    for n in ("computing-science", "engineering-science", "arts-and-social-sciences", "business", "science")) + "</main></body></html>"
def link_fetch(url, inst):
    seen.append(url); p = adm.Page(); p.raw = links_html; p.feed(links_html); return p, url
adm.fetch_page = link_fetch
def picked(program):
    seen.clear(); adm.collect("sfu", "requirements", program, 2027); return [u.rsplit("/", 1)[-1] for u in seen[1:]]
assert "computing-science.html" in picked("computing"), picked("computing")
assert "engineering-science.html" in picked("engineering"), picked("engineering")
assert "arts-and-social-sciences.html" in picked("arts"), picked("arts")
sci = picked("science")
assert "science.html" in sci and not {"computing-science.html", "engineering-science.html", "arts-and-social-sciences.html"} & set(sci), sci
# 10 percentages need admission context
assert not adm.has_evidence("they form 95% of the universe", "requirements")
assert adm.has_evidence("a minimum grade of 70% in English 12", "requirements")
assert adm.has_evidence("Admission averages: 88% to 93%", "history")
# 11 SFU-like: program menu + long general text, real requirements at the end must reach the model
menu = "".join(f"<li><a href='/students/admission/p{i}.html'>Program name number {i} in the faculty list</a></li>" for i in range(40))
general = "<p>Admission to SFU is competitive and the requirement varies; early admission is offered to applicants who apply by the deadline and send documents.</p>" * 25
req = "<h3>Required Courses</h3><p>Grade 11</p><p>Two of:</p><p>Chemistry 11</p><p>Physics 11</p><p>Grade 12 (at least 5 approved academic courses)</p><p>At least two of:</p><p>Calculus 12</p><p>Chemistry 12</p><p>All:</p><p>Pre-Calculus 12</p>"
sfu_html = f"<html><body><main><ul>{menu}</ul>{general}{req}</main></body></html>"
p = adm.Page(); p.raw = sfu_html; p.feed(sfu_html)
ex, _ = adm.excerpts(p.visible_text(), ("science",), "requirements", link_labels=[l for _, l in p.links])
head = ex[:2500]
assert "Pre-Calculus 12" in head and "Required Courses" in head and "Program name number 3" not in ex, head[:600]
# 12 UofT-like: provinces list, BC section goes first
prov = "".join(f"<h3>{n}</h3>" + f"<p>{n} secondary school diploma with six Grade 12 courses including English, with long explanatory text for applicants.</p>" * 6 for n in ("Alberta", "Ontario"))
uoft_html = f"<html><body><main>{prov}<h3>British Columbia</h3><p>High School Diploma with six Grade 12 academic subjects, including English.</p><p>English (ENG4U / EAE4U): English Studies 12</p><p>Advanced Functions (MHF4U): Pre-Calculus 12</p><h3>Manitoba</h3><p>Manitoba Grade 12 diploma text.</p></main></body></html>"
p = adm.Page(); p.raw = uoft_html; p.feed(uoft_html)
ex, _ = adm.excerpts(p.visible_text(), ("science",), "requirements")
assert ex.startswith("British Columbia") and "Manitoba" not in ex.split("…")[0], ex[:300]
# 13 SFU-like: requirement lines spread through a long page; the Required Courses block still comes first
spread = "".join(f"<p>Early admission note {i}: applicants presenting English Studies 12 or Chemistry 12 are reviewed in rounds with long explanatory text here.</p>" for i in range(30))
html13 = f"<html><body><main>{spread}{req}</main></body></html>"
p = adm.Page(); p.raw = html13; p.feed(html13)
ex, _ = adm.excerpts(p.visible_text(), ("science",), "requirements")
assert ex.startswith("Required Courses") and "Pre-Calculus 12" in ex[:600], ex[:300]
# 14 Queen's admission averages table
queens = "The table below corresponds to the minimum average (based on prerequisite courses) required for admission consideration for September of last year.\n| Arts (QA) |\n| Mid-80s |\n| Commerce* (QC) |\n| 90%+ |"
assert adm.has_evidence(queens, "history")
assert adm.has_evidence("| 90%+", "history") and adm.has_evidence("Life Sciences: high 80s", "history")
assert not adm.has_evidence("Grade 12 English (or their equivalents)", "history")
# 15 deadlines table keeps date/event alignment (UBC style: date first, event after)
ubc_dates = "<html><body><main>" + "<p>Key dates for applicants to UBC undergraduate programs in the 2027 winter session are listed below.</p>"*3 + "<table>" + "".join(
    f"<tr><td>{d}</td><td><a href='/applying-ubc/x'>{e}</a></td></tr>" for d, e in (
        ("Early October 2026", "Application opens"),
        ("November 15, 2026", "International Scholars application deadline"),
        ("December 1, 2026", "Canadian scholarship deadline"),
        ("January 15, 2027", "Applications due"))) + "</table></main></body></html>"
p = adm.Page(); p.raw = ubc_dates; p.feed(ubc_dates)
ex, _ = adm.excerpts(p.visible_text(), (), "deadlines", link_labels=[l for _, l in p.links])
for d, e in (("Early October 2026", "Application opens"), ("January 15, 2027", "Applications due"), ("November 15, 2026", "International Scholars")):
    row = next(line for line in ex.splitlines() if d in line)
    assert e in row, (d, row, ex)
# 16 optimistic false positives
assert not adm.has_evidence("Students must pass at least 70% of the required units", "requirements")
assert not adm.has_evidence("Send TOEFL score reports to 172 St. George St., Toronto", "language")
assert adm.has_evidence("IELTS Academic: overall band 6.5, no band below 6.0", "language")
print("all ok 2")
