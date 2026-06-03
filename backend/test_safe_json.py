"""Unit tests for the new brace-balanced _safe_json_loads."""
from app.agents.base import _safe_json_loads

cases = [
    ('direct', '{"a":1}', {'a': 1}),
    ('prose + json',
     '用户需要的是... {"goal":"x","conflict":"y"} 然后解释更多',
     {'goal': 'x', 'conflict': 'y'}),
    ('prose + nested json',
     '先来梳理 {"a":{"b":1,"c":[1,2]}} 后面还有',
     {'a': {'b': 1, 'c': [1, 2]}}),
    ('prose + json with string containing }',
     'hi {"a":"value with } brace", "b":2}',
     {'a': 'value with } brace', 'b': 2}),
    ('no json', 'pure prose, no braces', None),
    ('fenced json', '```json\n{"a":1}\n```', {'a': 1}),
    ('empty', '', None),
    ('unterminated', '{"a":1', None),
    ('two objects, first wins', '{"a":1} prose {"b":2}', {'a': 1}),
    ('chinese prose + json with quotes',
     '好的，章节规划如下：\n{"goal":"林萧被逐","conflict":"丹田废","beats":[{"name":"开场","summary":"描述","characters":["林萧"]}],"hook":"下章再见","foreshadows_to_advance":[],"foreshadows_to_pay_off":[],"must_follow":[],"avoid":[]}',
     {'goal': '林萧被逐', 'conflict': '丹田废', 'beats': [{'name': '开场', 'summary': '描述', 'characters': ['林萧']}], 'hook': '下章再见', 'foreshadows_to_advance': [], 'foreshadows_to_pay_off': [], 'must_follow': [], 'avoid': []}),
]

failed = 0
for name, inp, expected in cases:
    got = _safe_json_loads(inp)
    ok = got == expected
    print(f"  {'OK' if ok else 'FAIL'}: {name}")
    if not ok:
        print(f"    input:    {inp!r}")
        print(f"    expected: {expected!r}")
        print(f"    got:      {got!r}")
        failed += 1
print(f"\n{len(cases) - failed}/{len(cases)} pass")
exit(1 if failed else 0)
