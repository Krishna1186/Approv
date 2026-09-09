import json
from datetime import datetime,timezone
from unittest.mock import patch
from approv.harness.intent import RequestInterpreter
from approv.harness.inventory import import_off
from approv.harness.shopping import Action,Arm,RunConfig,Session,ShoppingCase
from approv.types.core import Channel,Constraint,Term


def setup():
    inv=import_off([{'code':'x','product_name':'Example','brands':'Example','quantity':'500 g'}],datetime.now(timezone.utc))[0]
    case=ShoppingCase(id='fixture',request='Please buy Example.',author='test fixture',cluster='fixture',
        constraints=(Constraint(attribute='brand',value=Term(surface='Example'),channel=Channel.AGENT_MESSAGE),))
    return inv,case


def test_original_request_mode_hides_interpretation_and_provider_metadata():
    inv,case=setup()
    session=Session(inv,case,Arm.BASELINE,RunConfig(expose_constraints=False))
    session.step(Action(type='search'),{'private_provider_metadata':'hidden'})
    text=json.dumps(session.observation())
    assert session.observation()['constraints']==[]
    assert 'private_provider_metadata' not in text
    assert 'private_provider_metadata' in json.dumps(session.result())


def test_description_available_on_inspection_for_every_arm():
    inv,case=setup()
    inv=inv.model_copy(update={'products':(inv.products[0].model_copy(update={'details':{'description':'Important variant information','brand':'Example'}}),)})
    for arm in Arm:
        session=Session(inv,case,arm,RunConfig(surface='verify'))
        search=session.step(Action(type='search'))
        assert 'description' not in search['products'][0]['details']
        detail=session.step(Action(type='inspect',product_id='x'))
        assert detail['product']['details']['description']=='Important variant information'


def response(reading):
    return {'model':'unit-fixture','choices':[{'finish_reason':'stop','message':{'content':json.dumps(reading)}}]}


def test_interpreter_never_receives_inventory_or_gold_and_rejects_fabricated_quotes():
    inv,case=setup()
    reading={'requirements':[{'attribute':'brand','value':{'kind':'term','surface':'Invented'},'quote':'never stated'}],
             'requested_units':7,'units_quote':'seven','unverified':[]}
    with patch('approv.harness.intent.post_json',return_value=response(reading)) as call:
        result,meta=RequestInterpreter('https://example.test','model','secret')(case,inv.category_schema)
    assert result.constraints==() and result.requested_units is None
    assert result.interpretation_notes
    sent=call.call_args.args[1]['messages'][1]['content']
    assert set(json.loads(sent))=={'request','attributes'}
    assert 'secret' not in json.dumps(meta)


def test_malformed_interpretation_retains_original_request_and_abstains_from_claims():
    inv,case=setup()
    original=case.model_copy(update={'constraints':()})
    with patch('approv.harness.intent.post_json',return_value=response({'requirements':'invalid'})):
        result,meta=RequestInterpreter('https://example.test','model','key')(original,inv.category_schema)
    assert result.request==original.request and result.constraints==()
    assert meta['status']=='invalid_interpretation'


def test_empty_valid_extraction_does_not_silently_imply_verification():
    inv,case=setup()
    with patch('approv.harness.intent.post_json',return_value=response({'requirements':[],'unverified':[]})):
        result,meta=RequestInterpreter('https://example.test','fixture','key','v3')(case,inv.category_schema)
    assert meta['supported_requirement_count']==0
    session=Session(inv,result,Arm.APPROV,RunConfig(surface='verify',expose_constraints=False))
    session.step(Action(type='search'))
    review=session.step(Action(type='select',product_id='x'))
    assert 'this is not verification' in review['approv']['feedback']


def test_native_tools_execute_one_declared_action_and_preserve_call_id():
    from approv.harness.adapters import ToolChatAgent
    data={'model':'fixture','choices':[{'finish_reason':'tool_calls','message':{'tool_calls':[
        {'id':'call-fixture','function':{'name':'search','arguments':'{"query":"Example"}'}}]}}]}
    with patch('approv.harness.adapters.post_json',return_value=data) as call:
        result=ToolChatAgent('https://example.test','fixture','key')({'request':'Example'})
    assert result.action==Action(type='search',query='Example')
    assert result.metadata['tool_call_id']=='call-fixture'
    payload=call.call_args.args[1]
    assert {t['function']['name'] for t in payload['tools']}=={'search','inspect','select','abstain'}


def test_native_history_uses_tool_response_roles():
    from approv.harness.adapters import ToolChatAgent
    data={'choices':[{'finish_reason':'tool_calls','message':{'tool_calls':[
        {'id':'next','function':{'name':'confirm_selection','arguments':'{"product_id":"x"}'}}]}}]}
    history=[{'kind':'action','payload':{'action':Action(type='select',product_id='x').model_dump()}},
             {'kind':'response','payload':{'status':'review','feedback':'Select again after review'}}]
    with patch('approv.harness.adapters.post_json',return_value=data) as call:
        ToolChatAgent('https://example.test','fixture','key')({'request':'Example','history':history})
    messages=call.call_args.args[1]['messages']
    assert [m['role'] for m in messages]==['system','user','assistant','tool','user']
    assert messages[-2]['tool_call_id']==messages[-3]['tool_calls'][0]['id']
    assert 'review' in messages[-2]['content']
    assert 'proposal' in messages[-1]['content']
    assert 'confirm_selection' in {t['function']['name'] for t in call.call_args.args[1]['tools']}


def test_native_tools_reject_multiple_or_unknown_calls():
    import pytest
    from approv.harness.adapters import ToolChatAgent,AdapterError
    for calls in ([{'function':{'name':'delete','arguments':'{}'}}],
                  [{'function':{'name':'search','arguments':'{}'}}]*2):
        data={'choices':[{'finish_reason':'tool_calls','message':{'tool_calls':calls}}]}
        with patch('approv.harness.adapters.post_json',return_value=data),pytest.raises(AdapterError):
            ToolChatAgent('https://example.test','fixture','key')({})


def test_v2_retains_valid_fields_when_model_invents_an_unsupported_attribute():
    inv,case=setup()
    reading={'requirements':[
        {'attribute':'invented','value':{'kind':'term','surface':'Example'},'quote':'Example'},
        {'attribute':'brand','value':{'kind':'term','surface':'Example'},'quote':'Example'}]}
    with patch('approv.harness.intent.post_json',return_value=response(reading)):
        result,meta=RequestInterpreter('https://example.test','fixture','key','v2')(case,inv.category_schema)
    assert len(result.constraints)==1 and result.constraints[0].attribute=='brand'
    assert result.interpretation_notes==('Unsupported requirement: invented',)
    assert meta['status']=='parsed'


def test_literal_check_repairs_total_per_pack_confusion_without_gold():
    from approv.harness.request_literals import repair_literals
    from approv.types.core import Quantity
    inv,case=setup()
    original=case.model_copy(update={'request':'Need 1.5 kg altogether. Use the 500 g packs.','constraints':()})
    wrong=original.model_copy(update={'constraints':(Constraint(attribute='net_weight',
        value=Quantity(magnitude='1.5',unit='kg',dimension='mass'),channel=Channel.AGENT_MESSAGE),)})
    fixed,changes=repair_literals(original,wrong,inv.category_schema)
    assert fixed.requested_units==3 and fixed.quantity_scope=='per_sale_unit'
    assert fixed.constraints[0].value==Quantity(magnitude='500',unit='g',dimension='mass')
    assert len(changes)==2


def test_literal_check_preserves_count_correction_and_does_not_use_party_size():
    from approv.harness.request_literals import repair_literals
    inv,case=setup()
    original=case.model_copy(update={'request':'There are 8 guests. Buy two packs. Actually make that three, each 500 g.'})
    fixed,_=repair_literals(original,original,inv.category_schema)
    assert fixed.requested_units==3


def test_literal_check_does_not_take_numeric_suffixes_or_negated_counts():
    from approv.harness.request_literals import repair_literals
    inv,case=setup()
    original=case.model_copy(update={'request':'Buy three packs, not two packs. Each is 1,050 g.'})
    fixed,_=repair_literals(original,original,inv.category_schema)
    assert fixed.requested_units==3
    assert not any(c.attribute=='net_weight' for c in fixed.constraints)
    original=case.model_copy(update={'request':'Buy twenty-two packs, each -500 g.','requested_units':None})
    fixed,_=repair_literals(original,original,inv.category_schema)
    assert fixed.requested_units is None
    assert not any(c.attribute=='net_weight' for c in fixed.constraints)


def test_type_mismatch_from_interpreter_does_not_crash_session():
    inv,case=setup()
    original=case.model_copy(update={'request':'Need 500 g of Example.','constraints':()})
    reading={'requirements':[{'attribute':'brand','value':{'kind':'quantity','magnitude':'500','unit':'g','dimension':'mass'},'quote':'500 g'}]}
    for version in ('v1','v2'):
        with patch('approv.harness.intent.post_json',return_value=response(reading)):
            result,meta=RequestInterpreter('https://example.test','fixture','key',version)(original,inv.category_schema)
        Session(inv,result,Arm.APPROV,RunConfig())
        assert result.constraints==()


def test_rate_limit_diagnostics_exclude_provider_message_and_identifiers():
    import io
    import urllib.error
    import pytest
    from approv.harness.adapters import post_json,AdapterError
    body=json.dumps({'error':{'type':'tokens','code':'rate_limit_exceeded',
        'failed_generation':'Unexpected echo: Bearer secret-key and secret-key',
        'message':'Tokens per day exceeded for organisation private-id; echoed secret-key'}}).encode()
    error=urllib.error.HTTPError('https://example.test',429,'Too Many Requests',
        {'retry-after':'477'},io.BytesIO(body))
    with patch('urllib.request.OpenerDirector.open',side_effect=error),pytest.raises(AdapterError) as caught:
        post_json('https://example.test',{}, {'Authorization':'Bearer secret-key'},1)
    assert caught.value.metadata['rate_limit_metric']=='tokens_per_day'
    assert caught.value.metadata['retry_after_seconds']==477
    assert 'secret-key' not in json.dumps(caught.value.metadata)
    assert 'private-id' not in json.dumps(caught.value.metadata)
    assert '[REDACTED]' in caught.value.metadata['provider_failed_generation']


def test_vocabulary_membership_uses_the_comparison_s_own_identity_key():
    """Measured 10 September on the shopper pack.

    The catalogue publishes availability as `in_stock`; the model writes "in stock".
    `compare_term` already treats those as the same value, because `normalize_term` folds
    the separator. The guard used raw casefold, so it rejected a requirement the operator
    would have matched, and the availability requirement was dropped on 4 of 46 held-out
    cases — on an attribute the answer key constrains on all 46. Dropping it lets a
    sold-out variant satisfy every field that was checked.
    """
    inv,case=setup()
    reading={'requirements':[{'attribute':'brand','value':{'kind':'term','surface':'in stock'},
                              'quote':'Example'}],'unverified':[]}
    interpreter=RequestInterpreter('https://example.test','model','key','v4',
                                   vocabulary={'brand':('in_stock','out_of_stock')})
    with patch('approv.harness.intent.post_json',return_value=response(reading)):
        result,meta=interpreter(case,inv.category_schema)

    assert meta['status']=='parsed'
    assert [c.value.surface for c in result.constraints]==['in stock']
    assert not any('outside the published vocabulary' in n for n in result.interpretation_notes)


def test_the_vocabulary_guard_still_refuses_to_widen_a_value():
    """Folding separators is not translating. The guard exists to stop "skin colored"
    becoming "beige", and it must still do that."""
    inv,case=setup()
    reading={'requirements':[{'attribute':'brand','value':{'kind':'term','surface':'skin colored'},
                              'quote':'Example'}],'unverified':[]}
    interpreter=RequestInterpreter('https://example.test','model','key','v4',
                                   vocabulary={'brand':('beige','black')})
    with patch('approv.harness.intent.post_json',return_value=response(reading)):
        result,_=interpreter(case,inv.category_schema)

    assert result.constraints==()
    assert any('outside the published vocabulary' in n for n in result.interpretation_notes)
