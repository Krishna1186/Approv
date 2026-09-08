"""Loopback test storefront for external agents and browsers. Never handles payments."""
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import random
import secrets
import threading

from approv.harness.experiment import save_experiment, validate_cases
from approv.harness.shopping import Action, Arm, Session, canonical, digest

HTML = r"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Approv Test Store</title><link rel="icon" href="data:,"><style>
body{font:16px system-ui;max-width:920px;margin:40px auto;padding:0 20px;color:#17242b;background:#fafaf7}
button,input{font:inherit;padding:10px;margin:4px;border:1px solid #9aa5a9;border-radius:4px}
button{cursor:pointer;background:#e7eee9}article{border-top:1px solid #ccd3d0;padding:18px 0}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}label{display:inline-block}h1{font-size:28px}
</style><h1>Test Store</h1><p>A frozen public inventory. Selections are recorded; no order is placed.</p>
<button id="start">Start next task</button><section id="task" hidden>
<h2 id="request"></h2><p id="scope"></p><details><summary>Recorded constraints</summary><pre id="constraints"></pre></details><p id="budget"></p>
<form id="search"><label>Search inventory <input id="query"></label><button>Search</button></form>
<button id="more" hidden>Next results</button><button id="abstain">Cannot fulfill request</button>
<div id="products"></div><pre id="feedback" role="status"></pre></section>
<script>
let token=null,nextOffset=null,lastQuery='';
async function api(path,body){let r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
let d=await r.json();if(!r.ok)throw Error(d.error||'Request failed');return d;}
function status(o){document.querySelector('#budget').textContent='Actions remaining: '+o.actions_remaining+' · '+o.status;
if(o.status!=='running'){document.querySelector('#start').hidden=false;document.querySelectorAll('#task button').forEach(b=>b.disabled=true);}}
async function action(a){try{let d=await api('/action',{token,action:a});status(d.observation);
document.querySelector('#feedback').textContent=d.response.error || (d.response.approv?.feedback ? d.response.feedback+'\n'+d.response.approv.feedback : d.response.feedback) || (d.response.status ? 'Selection status: '+d.response.status : 'Found '+d.response.total+' products.');
if(d.response.products)render(d.response.products);if(d.response.product)render([d.response.product]);
nextOffset=d.response.next_offset??null;document.querySelector('#more').hidden=nextOffset===null;
}catch(e){document.querySelector('#feedback').textContent=e.message;}}
function valueText(v){if(v.kind==='quantity')return v.magnitude+' '+v.unit;if(v.kind==='count')return String(v.n);if(v.kind==='money')return v.amount+' '+v.currency;return v.surface||JSON.stringify(v);}
function render(products){let root=document.querySelector('#products');root.replaceChildren();for(let p of products){
let row=document.createElement('article'),title=document.createElement('h3'),id=document.createElement('p'),facts=document.createElement('dl');
title.textContent=p.title;id.textContent='Product '+p.id;row.append(title,id);
for(let [key,text] of Object.entries(p.details||{})){let name=document.createElement('dt'),value=document.createElement('dd');name.textContent=key;value.textContent=text;facts.append(name,value);}
for(let e of p.evidence){if(e.field_name==='product_name')continue;let name=document.createElement('dt'),value=document.createElement('dd');name.textContent=e.attribute.replaceAll('_',' ');value.textContent=valueText(e.value);facts.append(name,value);}row.append(facts);
if(p.approv){let note=document.createElement('pre');note.textContent=p.approv.feedback+'\nAssessed sale units: '+p.approv.assessed_sale_units;row.append(note);}
let sources=document.createElement('details'),summary=document.createElement('summary'),detail=document.createElement('pre');summary.textContent='Source fields';detail.textContent=JSON.stringify(p.evidence,null,2);sources.append(summary,detail);row.append(sources);
let label=document.createElement('label'),units=document.createElement('input');label.textContent='Sale units ';units.type='number';units.min=1;units.max=100;units.value=1;label.append(units);row.append(label);
let inspect=document.createElement('button');inspect.textContent='Inspect';inspect.onclick=()=>action({type:'inspect',product_id:p.id});row.append(inspect);
let select=document.createElement('button');select.textContent='Select';select.onclick=()=>action({type:'select',product_id:p.id,units:Number(units.value)});row.append(select);root.append(row);}}
document.querySelector('#start').onclick=async()=>{try{let d=await api('/task',{});if(d.done){document.querySelector('#start').textContent='Experiment complete';document.querySelector('#start').disabled=true;return;}
token=d.token;document.querySelector('#task').hidden=false;document.querySelector('#start').hidden=true;
document.querySelectorAll('#task button').forEach(b=>b.disabled=false);document.querySelector('#products').replaceChildren();document.querySelector('#feedback').textContent='';
document.querySelector('#query').value='';nextOffset=null;document.querySelector('#more').hidden=true;document.querySelector('#scope').textContent='Quantities: '+d.observation.quantity_scope.replaceAll('_',' ')+'; requested sale units: '+(d.observation.requested_sale_units??'unspecified');document.querySelector('#request').textContent=d.observation.request;document.querySelector('#constraints').textContent=JSON.stringify({constraints:d.observation.constraints,instructions:d.observation.instructions},null,2);status(d.observation);
}catch(e){document.querySelector('#feedback').textContent=e.message;}};
document.querySelector('#search').onsubmit=e=>{e.preventDefault();lastQuery=document.querySelector('#query').value;action({type:'search',query:lastQuery});};
document.querySelector('#more').onclick=()=>action({type:'search',query:lastQuery,offset:nextOffset});
document.querySelector('#abstain').onclick=()=>action({type:'abstain'});
</script></html>"""


class Store:
    def __init__(self, inventory, cases, config, output: Path, agent_name: str):
        validate_cases(cases)
        if output.exists():
            raise FileExistsError(output)
        self.inventory, self.cases, self.config, self.output = inventory, cases, config, output
        self.tasks = [(c, a) for c in cases for a in Arm]
        random.Random(config.seed).shuffle(self.tasks)
        self.results = []
        self.current = None
        self.token = None
        self.lock = threading.Lock()
        self.agent_name = agent_name

    def task(self):
        if self.current is None or self.current.status != "running":
            if len(self.results) == len(self.tasks):
                return {"done": True}
            case, arm = self.tasks[len(self.results)]
            self.current = Session(self.inventory, case, arm, self.config)
            self.token = secrets.token_urlsafe(24)
        return {"token": self.token, "observation": self.current.observation()}

    def action(self, token, raw):
        if not self.token or not secrets.compare_digest(str(token), self.token):
            raise ValueError("unknown session token")
        response = self.current.step(Action.model_validate(raw))
        observation = self.current.observation()
        if self.current.status != "running":
            result = self.current.result()
            self.results.append(result)
            # Durable individual sessions survive an interrupted external run.
            checkpoint = self.output.with_name(self.output.name + f".session-{len(self.results):04d}.json")
            with checkpoint.open("x", encoding="utf-8") as file:
                file.write(canonical(result))
            if len(self.results) == len(self.tasks):
                manifest = {"version": "experiment-v1", "date": datetime.now(timezone.utc).isoformat(),
                    "inventory_hash": digest(self.inventory),
                    "cases_hash": digest([c.model_dump(mode="json") for c in self.cases]),
                    "config": self.config.model_dump(mode="json"),
                    "agent": {"transport": "external_storefront", "name": self.agent_name,
                              "isolation": "external operator must reset agent context for each task"},
                    "schedule": [{"case_id": c.id, "arm": a.value} for c, a in self.tasks],
                    "results_hash": digest(self.results)}
                save_experiment(self.output, {"manifest": manifest, "results": self.results})
        return {"response": response, "observation": observation}


def make_server(store: Store, port=8765):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, code, data, content_type="application/json"):
            raw = data.encode() if isinstance(data, str) else canonical(data).encode()
            self.send_response(code)
            self.send_header("Content-Type", content_type + "; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(raw)

        def allowed(self):
            host = self.headers.get("Host", "")
            allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            origin = self.headers.get("Origin")
            return host in allowed and (origin is None or origin == "http://" + host)

        def do_GET(self):
            if not self.allowed():
                return self.reply(403, {"error": "loopback origin required"})
            if self.path == "/":
                return self.reply(200, HTML, "text/html")
            return self.reply(404, {"error": "not found"})

        def do_POST(self):
            if not self.allowed():
                return self.reply(403, {"error": "loopback origin required"})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 16384 or self.headers.get_content_type() != "application/json":
                    return self.reply(400, {"error": "small JSON body required"})
                body = json.loads(self.rfile.read(size))
                with store.lock:
                    if self.path == "/task":
                        result = store.task()
                    elif self.path == "/action":
                        result = store.action(body["token"], body["action"])
                    else:
                        return self.reply(404, {"error": "not found"})
                self.reply(200, result)
            except (ValueError, KeyError, TypeError):
                self.reply(400, {"error": "invalid action, body or session state"})

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
