"""Generate p15_load_test.jmx (Apache JMeter 5.6) for Lab 2 Part 5.

    python jmeter/build_plan.py          # writes jmeter/p15_load_test.jmx

Five thread groups, each switched on by a property (0 users = off), so one
plan covers every endpoint and level:

    jmeter -n -t jmeter/p15_load_test.jmx -Jendpoint_users=... (see run_all.sh)

  Login                POST /users/login                    login_users
  Job search           GET  /jobs/search?q=&location=&category=   search_users
  Application          POST /applications (Kafka in Lab 2)  apply_users
  Event search         GET  /events/search?q=&location=     event_users
  Assistant            POST /assistant/chat                 assistant_users

Non-login groups use tokens prepared by make_data.py (tokens.csv), so they
measure their endpoint rather than bcrypt; login is measured on its own.
Application submission accepts 201/202 (created / queued) and 409 (already
applied: the correct answer for a duplicate) as success.

Common properties: host (localhost), port (9150), protocol (http),
ramp (seconds, 30), duration (seconds, 60), data_dir (data, relative to the .jmx),
timeout_ms (60000; the assistant group uses assistant_timeout_ms, 300000).
"""
from pathlib import Path
from xml.etree import ElementTree as ET

OUT = Path(__file__).with_name("p15_load_test.jmx")


def el(tag, attrs=None, text=None, children=()):
    node = ET.Element(tag, attrs or {})
    if text is not None:
        node.text = text
    for child in children:
        node.append(child)
    return node


def prop(kind, name, value):
    return el(f"{kind}Prop", {"name": name}, str(value).lower() if kind == "bool" else str(value))


def tree(*pairs):
    """[(element, [children...])] -> JMeter's element/hashTree alternation."""
    ht = el("hashTree")
    for element, children in pairs:
        ht.append(element)
        ht.append(tree(*children) if children else el("hashTree"))
    return ht


def arguments(name="HTTPsampler.Arguments", items=()):
    return el("elementProp", {"name": name, "elementType": "Arguments", "guiclass": "HTTPArgumentsPanel",
                              "testclass": "Arguments", "testname": "Variables"},
              children=[el("collectionProp", {"name": "Arguments.arguments"}, children=list(items))])


def sampler(name, method, path, body=None):
    s = el("HTTPSamplerProxy", {"guiclass": "HttpTestSampleGui", "testclass": "HTTPSamplerProxy",
                                "testname": name, "enabled": "true"})
    if body is not None:
        s.append(prop("bool", "HTTPSampler.postBodyRaw", True))
        s.append(arguments(items=[el("elementProp", {"name": "", "elementType": "HTTPArgument"}, children=[
            prop("bool", "HTTPArgument.always_encode", False),
            prop("string", "Argument.value", body),
            prop("string", "Argument.metadata", "=")])]))
    else:
        s.append(arguments())
    for k, v in (("HTTPSampler.path", path), ("HTTPSampler.method", method)):
        s.append(prop("string", k, v))
    s.append(prop("bool", "HTTPSampler.follow_redirects", True))
    s.append(prop("bool", "HTTPSampler.use_keepalive", True))
    return s


def headers(name, pairs):
    return el("HeaderManager", {"guiclass": "HeaderPanel", "testclass": "HeaderManager", "testname": name},
              children=[el("collectionProp", {"name": "HeaderManager.headers"}, children=[
                  el("elementProp", {"name": "", "elementType": "Header"},
                     children=[prop("string", "Header.name", k), prop("string", "Header.value", v)])
                  for k, v in pairs])])


def csv(name, filename, variables, share="shareMode.all"):
    return el("CSVDataSet", {"guiclass": "TestBeanGUI", "testclass": "CSVDataSet", "testname": name},
              children=[prop("string", "filename", "${__P(data_dir,data)}/" + filename),
                        prop("string", "fileEncoding", "UTF-8"),
                        prop("string", "variableNames", variables),
                        prop("bool", "ignoreFirstLine", True),
                        prop("string", "delimiter", ","),
                        prop("bool", "quotedData", False),
                        prop("bool", "recycle", True),
                        prop("bool", "stopThread", False),
                        prop("string", "shareMode", share)])


def assert_codes(name, pattern):
    # assume_success=true: JMeter does not fail non-2xx by itself; this
    # assertion decides (so 409 can count as a correct answer).
    return el("ResponseAssertion", {"guiclass": "AssertionGui", "testclass": "ResponseAssertion",
                                    "testname": name},
              children=[el("collectionProp", {"name": "Asserion.test_strings"},
                           children=[prop("string", "codes", pattern)]),
                        prop("string", "Assertion.custom_message", f"expected HTTP {pattern}"),
                        prop("string", "Assertion.test_field", "Assertion.response_code"),
                        prop("bool", "Assertion.assume_success", True),
                        prop("int", "Assertion.test_type", 1)])          # 1 = Matches (regex)


def json_extract(var, path):
    return el("JSONPostProcessor", {"guiclass": "JSONPostProcessorGui", "testclass": "JSONPostProcessor",
                                    "testname": f"extract {var}"},
              children=[prop("string", "JSONPostProcessor.referenceNames", var),
                        prop("string", "JSONPostProcessor.jsonPathExprs", path),
                        prop("string", "JSONPostProcessor.match_numbers", "1"),
                        prop("string", "JSONPostProcessor.defaultValues", "NOT_FOUND")])


def thread_group(name, users_prop, timeout_prop="timeout_ms", timeout_default="60000"):
    return el("ThreadGroup", {"guiclass": "ThreadGroupGui", "testclass": "ThreadGroup",
                              "testname": name, "enabled": "true"}, children=[
        prop("string", "ThreadGroup.on_sample_error", "continue"),
        el("elementProp", {"name": "ThreadGroup.main_controller", "elementType": "LoopController",
                           "guiclass": "LoopControlPanel", "testclass": "LoopController",
                           "testname": "Loop Controller"},
           children=[prop("bool", "LoopController.continue_forever", False),
                     prop("int", "LoopController.loops", -1)]),
        prop("string", "ThreadGroup.num_threads", "${__P(%s,0)}" % users_prop),
        prop("string", "ThreadGroup.ramp_time", "${__P(ramp,30)}"),
        prop("bool", "ThreadGroup.scheduler", True),
        prop("string", "ThreadGroup.duration", "${__P(duration,60)}"),
        prop("string", "ThreadGroup.delay", "0"),
        prop("bool", "ThreadGroup.same_user_on_next_iteration", True),
    ]), ("${__P(%s,%s)}" % (timeout_prop, timeout_default))


def with_timeout(sampler_el, timeout):
    sampler_el.append(prop("string", "HTTPSampler.response_timeout", timeout))
    return sampler_el


def build():
    plan = el("TestPlan", {"guiclass": "TestPlanGui", "testclass": "TestPlan",
                           "testname": "p15 Handshake load test (Lab 2 Part 5)"}, children=[
        prop("string", "TestPlan.comments",
             "Generated by jmeter/build_plan.py. Enable a group with -J<group>_users=N."),
        prop("bool", "TestPlan.functional_mode", False),
        prop("bool", "TestPlan.serialize_threadgroups", False),
        arguments("TestPlan.user_defined_variables")])

    defaults = el("ConfigTestElement", {"guiclass": "HttpDefaultsGui", "testclass": "ConfigTestElement",
                                        "testname": "HTTP defaults (gateway)"}, children=[
        arguments(),
        prop("string", "HTTPSampler.domain", "${__P(host,localhost)}"),
        prop("string", "HTTPSampler.port", "${__P(port,9150)}"),
        prop("string", "HTTPSampler.protocol", "${__P(protocol,http)}"),
        prop("string", "HTTPSampler.connect_timeout", "10000"),
        prop("string", "HTTPSampler.implementation", "HttpClient4")])
    json_headers = headers("JSON content type", [("Content-Type", "application/json")])
    auth = lambda: headers("Bearer token + trace id",  # noqa: E731
                           [("Authorization", "Bearer ${token}"),
                            ("X-Trace-Id", "jmeter-${__threadNum}-${__counter(TRUE,)}")])

    login_tg, t = thread_group("Login", "login_users")
    login = with_timeout(sampler("POST /users/login", "POST", "/users/login",
                                 '{"email":"${email}","password":"${password}"}'), t)

    search_tg, t = thread_group("Job search", "search_users")
    search = with_timeout(sampler("GET /jobs/search", "GET",
                                  "/jobs/search?q=${term}&location=${city}&category=${category}"), t)

    apply_tg, t = thread_group("Application submission", "apply_users")
    apply = with_timeout(sampler("POST /applications", "POST", "/applications",
                                 '{"job_id":${job_id},"resume_id":${resume_id}}'), t)

    event_tg, t = thread_group("Event search", "event_users")
    event = with_timeout(sampler("GET /events/search", "GET",
                                 "/events/search?q=${event_term}&location=${city}"), t)

    assistant_tg, t = thread_group("Assistant chat", "assistant_users",
                                   "assistant_timeout_ms", "300000")
    assistant = with_timeout(sampler("POST /assistant/chat", "POST", "/assistant/chat",
                                     '{"message":"${prompt}"}'), t)

    root = el("jmeterTestPlan", {"version": "1.2", "properties": "5.0", "jmeter": "5.6.3"})
    root.append(tree((plan, [
        (defaults, []),
        (json_headers, []),
        (login_tg, [(csv("students.csv", "students.csv", "email,password,student_id,resume_id"), []),
                    (login, [(assert_codes("200", "200"), [])])]),
        (search_tg, [(csv("tokens.csv", "tokens.csv", "token,student_id,resume_id"), []),
                     (csv("search_terms.csv", "search_terms.csv", "term,city,category"), []),
                     (auth(), []),
                     (search, [(assert_codes("200", "200"), [])])]),
        (apply_tg, [(csv("tokens.csv", "tokens.csv", "token,student_id,resume_id"), []),
                    (csv("open_jobs.csv", "open_jobs.csv", "job_id"), []),
                    (auth(), []),
                    (apply, [(assert_codes("201, 202 or 409", "201|202|409"), [])])]),
        (event_tg, [(csv("tokens.csv", "tokens.csv", "token,student_id,resume_id"), []),
                    (csv("search_terms.csv", "search_terms.csv", "term,city,category"), []),
                    (csv("event_terms.csv", "event_terms.csv", "event_term"), []),
                    (auth(), []),
                    (event, [(assert_codes("200", "200"), [])])]),
        (assistant_tg, [(csv("tokens.csv", "tokens.csv", "token,student_id,resume_id"), []),
                        (csv("prompts.csv", "prompts.csv", "prompt"), []),
                        (auth(), []),
                        (assistant, [(assert_codes("200", "200"), []),
                                     (json_extract("assistant_status", "$.status"), [])])]),
    ])))
    ET.indent(root, space="  ")
    OUT.write_text('<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    build()
