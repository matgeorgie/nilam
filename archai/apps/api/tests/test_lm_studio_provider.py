import json

import httpx
import pytest

from app.ai.local_model import FloorDecision, LMStudioModel


def test_structured_output_from_qwen_reasoning_field():
    requests=[]
    body={'rooms':[{'type':'kitchen','name':'Kitchen','count':1,
                    'preferred_floor':0,'attached_bathroom':False}], 'questions':[]}

    def handle(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop',
            'message':{'content':'','reasoning_content':json.dumps(body)}}]})

    client=httpx.Client(transport=httpx.MockTransport(handle))
    result=LMStudioModel(client).create_chat_completion(
        messages=[{'role':'user','content':'One kitchen'}],temperature=0,max_tokens=400,
        response_format={'type':'json_object','schema':FloorDecision.model_json_schema()})
    assert FloorDecision.model_validate_json(result['choices'][0]['message']['content']).rooms[0].type=='kitchen'
    assert requests[0]['model']=='qwen/qwen3.5-9b'
    assert requests[0]['response_format']['type']=='json_schema'
    assert requests[0]['response_format']['json_schema']['schema']==FloorDecision.model_json_schema()


def test_unavailable_lm_studio_reports_error_without_fallback():
    def unavailable(request):
        raise httpx.ConnectError('offline',request=request)

    client=httpx.Client(transport=httpx.MockTransport(unavailable))
    with pytest.raises(RuntimeError,match='LM Studio is unavailable'):
        LMStudioModel(client).create_chat_completion(
            messages=[],temperature=0,max_tokens=50,
            response_format={'type':'json_object','schema':FloorDecision.model_json_schema()})


def test_reasoning_prose_is_not_used_as_structured_result():
    client=httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(
        200,json={'choices':[{'finish_reason':'stop',
            'message':{'content':'','reasoning_content':'thinking, not JSON'}}]})))
    with pytest.raises(RuntimeError,match='complete structured JSON'):
        LMStudioModel(client).create_chat_completion(
            messages=[],temperature=0,max_tokens=50,
            response_format={'type':'json_object','schema':FloorDecision.model_json_schema()})
