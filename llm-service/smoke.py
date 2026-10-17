"""Run inside a gateway Pod: kubectl exec -i ... -- python < smoke.py.

Reads existing caller credentials from the environment; never prints credentials.
"""
import json
import os
import httpx

token = os.environ['LLM_TOKEN_DAOFAZIRAN']
with httpx.Client(base_url='http://127.0.0.1:8000', timeout=150, headers={'Authorization': 'Bearer '+token}) as client:
    ready = client.get('/health/ready')
    ready.raise_for_status()
    routes = ready.json()['routes']
    for tier in ('guarded', 'trusted'):
        model = 'llm-'+tier
        response = client.post('/v1/chat/completions', json={'model':model,'messages':[{'role':'user','content':'Reply with OK.'}],'max_tokens':128})
        response.raise_for_status()
        assert response.json()['choices']
        assert response.headers['X-LLM-Route-Revision'] == routes[model]['route_revision']
        print(model, routes[model]['resolved_upstream'], 'text OK', flush=True)
    response = client.post('/v1/chat/completions', json={'model':'llm-trusted','messages':[{'role':'user','content':'Return a JSON object with status equal to ok.'}],'max_tokens':128,'response_format':{'type':'json_object'}})
    response.raise_for_status()
    assert isinstance(json.loads(response.json()['choices'][0]['message']['content']), dict)
    print('trusted JSON OK', flush=True)
    response = client.post('/v1/chat/completions', json={'model':'llm-trusted','messages':[{'role':'user','content':'Call echo with text ok.'}], 'max_tokens':2048,'tools':[{'type':'function','function':{'name':'echo','parameters':{'type':'object','properties':{'text':{'type':'string'}},'required':['text']}}}],'tool_choice':'auto'})
    response.raise_for_status()
    assert response.json()['choices'][0]['message']['tool_calls']
    print('trusted tools OK', flush=True)
    with client.stream('POST','/v1/chat/completions',json={'model':'llm-guarded','messages':[{'role':'user','content':'Reply with OK.'}],'max_tokens':128,'stream':True}) as response:
        response.raise_for_status()
        assert response.headers['X-LLM-Route-Revision'] == routes['llm-guarded']['route_revision']
        body = ''.join(response.iter_text())
        assert 'data:' in body and '[DONE]' in body
    print('guarded SSE OK', flush=True)
    response=client.post('/v1/chat/completions',json={'model':'llm-guarded','messages':[{'role':'user','content':'JSON please'}],'response_format':{'type':'json_object'}})
    assert response.status_code == 400
    print('guarded restriction OK', flush=True)
