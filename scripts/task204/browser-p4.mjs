import assert from 'node:assert/strict';
import {spawn, execFileSync} from 'node:child_process';
import {mkdtemp,readFile,writeFile} from 'node:fs/promises';
import path from 'node:path';
if (!process.argv[2]) throw Error('Usage: node browser-p4.mjs <local-evidence-directory>');
const dir=path.resolve(process.argv[2]);
const repo=path.resolve(import.meta.dirname,'../..');
const privateData=JSON.parse(await readFile(path.join(dir,'browser.private.local.json'),'utf8'));
const profile=await mkdtemp(path.join(dir,'chrome-real-'));
const chrome=spawn('C:/Program Files/Google/Chrome/Application/chrome.exe',[
 '--headless=new','--remote-debugging-port=0','--disable-background-networking','--disable-component-update',
 '--no-first-run','--user-data-dir='+profile,'about:blank'],{windowsHide:true,stdio:'ignore'});
const delay=ms=>new Promise(r=>setTimeout(r,ms));
async function until(fn,label){const end=Date.now()+30000;while(Date.now()<end){const x=await fn();if(x)return x;await delay(150);}throw Error('Timeout: '+label);}
let ws,diagnosticRead;
try{
 const port=await until(async()=>{try{return(await readFile(path.join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0]}catch{return null}},'Chrome');
 const target=await(await fetch(`http://127.0.0.1:${port}/json/new?about:blank`,{method:'PUT'})).json();
 ws=new WebSocket(target.webSocketDebuggerUrl);const pending=new Map();let id=0,posts=0,dropped=false;
 const call=(method,params={})=>new Promise((resolve,reject)=>{const key=++id;pending.set(key,{resolve,reject});ws.send(JSON.stringify({id:key,method,params}));});
 ws.addEventListener('message',({data})=>{const msg=JSON.parse(data);if(pending.has(msg.id)){const p=pending.get(msg.id);pending.delete(msg.id);msg.error?p.reject(Error(msg.error.message)):p.resolve(msg.result);}
  if(msg.method==='Network.requestWillBeSent'&&msg.params.request.method==='POST'&&msg.params.request.url.endsWith('/confirm-source'))posts++;
  if(msg.method==='Fetch.requestPaused'){
   const p=msg.params;if(!dropped&&p.request.method==='POST'&&p.responseStatusCode===200){dropped=true;call('Fetch.failRequest',{requestId:p.requestId,errorReason:'ConnectionReset'}).catch(()=>{});}
   else call('Fetch.continueRequest',{requestId:p.requestId}).catch(()=>{});
  }});
 await new Promise((r,j)=>{ws.addEventListener('open',r,{once:true});ws.addEventListener('error',j,{once:true})});
 const evaluate=async expression=>{const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.text);return r.result.value};
 diagnosticRead=()=>evaluate('({path:location.pathname,body:document.body.innerText})');
 await call('Page.enable');await call('Network.enable');
 await call('Page.navigate',{url:'http://127.0.0.1:3000/'});
 await until(()=>evaluate('document.readyState==="complete"'),'page');
 const account=privateData.accounts[0];
 assert.equal(await evaluate(`(async()=>{const {getSupabase}=await import('/src/services/supabase.js');const {error}=await getSupabase().auth.setSession(${JSON.stringify({access_token:account.access_token,refresh_token:account.refresh_token})});return !error})()`),true);
 await call('Page.navigate',{url:`http://127.0.0.1:3000/session/${privateData.session_id}/stage1`});
 await until(()=>evaluate(`document.body.innerText.includes('Giải phương trình')`),'real source preview');
 await call('Fetch.enable',{patterns:[{urlPattern:'*/confirm-source',requestStage:'Response'}]});
 await until(()=>evaluate(`(()=>{const b=[...document.querySelectorAll('button')].find(b=>b.textContent.includes('Xác nhận đề gốc và tiếp tục'));if(!b||b.disabled)return false;b.focus();return true})()`),'confirm');
 for(const type of ['keyDown','keyUp'])await call('Input.dispatchKeyEvent',{type,key:' ',code:'Space',windowsVirtualKeyCode:32,text:type==='keyDown'?' ':undefined});
 await until(()=>dropped,'drop committed response');
 await call('Fetch.disable');await call('Page.reload');
 await until(()=>evaluate('location.pathname.endsWith("/stage2")'),'F5 handoff');
 const locked=await until(()=>evaluate(`(()=>{const b=document.querySelector('button[type="submit"]');return b?b.disabled:null})()`),'pending locked');
 assert.equal(locked,true);assert.equal(posts,1);
 execFileSync('docker',['run','--rm','--network','container:supabase_kong_task204-supabase-local',
 '--mount',`type=bind,source=${repo},target=/repo,readonly`,
 '--mount',`type=bind,source=${dir},target=/evidence`,'--entrypoint','python','exam-tv1-local-backend','/repo/scripts/task204/produce_browser.py'],{windowsHide:true,stdio:'pipe',timeout:60000});
 await call('Page.reload');
 await until(()=>evaluate(`(()=>{const b=document.querySelector('button[type="submit"]');return b&&!b.disabled})()`),'ready form');
 assert.equal(posts,1);
 await writeFile(path.join(dir,'browser-real-result.json'),JSON.stringify({passed:true,auth:'real Supabase Local JWT',http:'real app proxy/backend/PostgREST',keyboardConfirm:true,droppedCommittedResponse:true,F5SameSession:true,confirmPosts:posts,pendingLocked:true,readyEmptyModesUnlockedAfterF5:true,provider:'fake algebra; no Gemini keys'},null,2));
 console.log('PASS: real browser confirm/response loss/F5/Stage2 pending and ready');
}catch(error){if(diagnosticRead)console.error(JSON.stringify(await diagnosticRead()));throw error;}finally{ws?.close();chrome.kill();}
