import test from 'node:test';
import assert from 'node:assert/strict';
import {ApiError,demo} from '../lib/api.ts';

function setup(initialToken,responses){
  const values=new Map(initialToken?[['archai-session',initialToken]]:[]);
  globalThis.window={};
  globalThis.localStorage={
    getItem:key=>values.get(key)??null,
    setItem:(key,value)=>values.set(key,value),
    removeItem:key=>values.delete(key),
  };
  const calls=[];
  globalThis.fetch=async(url,options)=>{
    calls.push({url,authorization:options.headers.Authorization});
    const next=responses.shift();
    assert.ok(next,'Unexpected API request');
    return new Response(JSON.stringify(next.body),{status:next.status,headers:{'Content-Type':'application/json'}});
  };
  return {calls,values};
}

test('demo recovers from an expired saved session exactly once',async()=>{
  const {calls,values}=setup('expired',[
    {status:401,body:{detail:'Please sign in to continue.'}},
    {status:200,body:{token:'fresh'}},
    {status:200,body:{id:'demo-project'}},
  ]);
  assert.equal((await demo()).id,'demo-project');
  assert.deepEqual(calls.map(call=>new URL(call.url).pathname),['/api/projects/demo','/api/auth/demo','/api/projects/demo']);
  assert.deepEqual(calls.map(call=>call.authorization),['Bearer expired','Bearer ','Bearer fresh']);
  assert.equal(values.get('archai-session'),'fresh');
});

test('demo reuses a valid session',async()=>{
  const {calls}=setup('valid',[{status:200,body:{id:'demo-project'}}]);
  assert.equal((await demo()).id,'demo-project');
  assert.equal(calls.length,1);
});

test('demo does not retry non-authentication failures',async()=>{
  const {calls}=setup('valid',[{status:422,body:{detail:'No valid layout'}}]);
  await assert.rejects(demo(),error=>error instanceof ApiError&&error.status===422);
  assert.equal(calls.length,1);
});

test('demo does not loop when a renewed session is rejected',async()=>{
  const {calls}=setup('expired',[
    {status:401,body:{detail:'Please sign in to continue.'}},
    {status:200,body:{token:'fresh'}},
    {status:401,body:{detail:'Please sign in to continue.'}},
  ]);
  await assert.rejects(demo(),error=>error instanceof ApiError&&error.status===401);
  assert.equal(calls.length,3);
});
