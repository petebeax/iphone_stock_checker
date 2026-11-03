'use strict';
const OWNER='petebeax', REPO='iphone_stock_checker', BRANCH='main';
const API=`https://api.github.com/repos/${OWNER}/${REPO}/contents/`;
const $=id=>document.getElementById(id);
let watches=[], catalog=[], fileSHA=null, unlocked=false;
const enc=new TextEncoder(), dec=new TextDecoder();
const b64=u=>btoa(Array.from(u,x=>String.fromCharCode(x)).join(''));
const from64=s=>Uint8Array.from(atob(s),c=>c.charCodeAt(0));
const status=(id,msg,error=false)=>{const e=$(id);e.textContent=msg;e.className=`status ${error?'error':'success'}`;};
async function derive(pass,salt){let material=await crypto.subtle.importKey('raw',enc.encode(pass),'PBKDF2',false,['deriveKey']);return crypto.subtle.deriveKey({name:'PBKDF2',salt,iterations:250000,hash:'SHA-256'},material,{name:'AES-GCM',length:256},false,['encrypt','decrypt']);}
async function seal(list,pass){const salt=crypto.getRandomValues(new Uint8Array(16)), iv=crypto.getRandomValues(new Uint8Array(12));const key=await derive(pass,salt);const ciphertext=await crypto.subtle.encrypt({name:'AES-GCM',iv},key,enc.encode(JSON.stringify(list)));return {v:1,salt:b64(salt),iv:b64(iv),data:b64(new Uint8Array(ciphertext))};}
async function openEnvelope(payload,pass){if(payload.v!==1)throw Error('Unsupported encrypted format');const key=await derive(pass,from64(payload.salt));let plaintext;try{plaintext=await crypto.subtle.decrypt({name:'AES-GCM',iv:from64(payload.iv)},key,from64(payload.data));}catch(_){throw Error('Incorrect passphrase or damaged encrypted watchlist');}const parsed=JSON.parse(dec.decode(plaintext));if(!Array.isArray(parsed))throw Error('Watchlist must be an array');return parsed;}
function apiHeaders(auth=false){const h={'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'};if(auth)h.Authorization='Bearer '+$('token').value.trim();return h;}
async function getRepoFile(name,privateAuth=false){const r=await fetch(API+encodeURIComponent(name)+'?ref='+BRANCH,{headers:apiHeaders(privateAuth),cache:'no-store'});if(r.status===404)return null;if(!r.ok)throw Error('GitHub HTTP '+r.status+' while reading '+name);return r.json();}
async function fetchCatalog(){try{const r=await fetch(`https://raw.githubusercontent.com/${OWNER}/${REPO}/${BRANCH}/catalog.json?cacheBust=${Date.now()}`,{cache:'no-store'});if(!r.ok)throw Error('Catalog not yet published');const items=await r.json();if(!Array.isArray(items)||!items.length)throw Error('Catalog is empty');catalog=items.filter(v=>v.model&&v.storage&&v.color&&v.part);status('authStatus',`Loaded ${catalog.length} Apple configurations.`);}catch(e){catalog=[];status('authStatus',`Apple catalogue unavailable (${e.message}). Run the stock-check workflow once to publish catalog.json.`,true);}}
function opt(select,values,value){select.replaceChildren();for(const str of values){const op=document.createElement('option');op.value=str;op.textContent=str;select.append(op);}if(values.includes(value))select.value=value;}
function input(labelTxt,value,type='text'){const label=document.createElement('label');label.textContent=labelTxt;const element=document.createElement('input');element.type=type;element.value=value||'';label.append(element);return {label,element};}
function selectField(labelTxt){const label=document.createElement('label');label.textContent=labelTxt;const element=document.createElement('select');label.append(element);return {label,element};}
function render(){const container=$('entries');container.replaceChildren();watches.forEach((w,i)=>{
 const article=document.createElement('article');article.className='entry';
 const head=document.createElement('div');head.className='entry-head';const title=document.createElement('h3');title.textContent=`Phone ${i+1}`;const remove=document.createElement('button');remove.textContent='Remove';remove.className='danger';remove.onclick=()=>{watches.splice(i,1);render();};head.append(title,remove);article.append(head);
 const grid=document.createElement('div');grid.className='grid';
 const model=selectField('iPhone model'), storage=selectField('Storage'), color=selectField('Colour');
 const unique=items=>[...new Set(items)].sort((a,b)=>a.localeCompare(b,undefined,{numeric:true}));
 function refreshModels(){opt(model.element,unique(catalog.map(v=>v.model)),w.model);w.model=model.element.value;refreshStorage();}
 function refreshStorage(){opt(storage.element,unique(catalog.filter(v=>v.model===w.model).map(v=>v.storage)),w.storage);w.storage=storage.element.value;refreshColor();}
 function refreshColor(){opt(color.element,unique(catalog.filter(v=>v.model===w.model&&v.storage===w.storage).map(v=>v.color)),w.color);w.color=color.element.value;}
 model.element.onchange=()=>{w.model=model.element.value;w.storage='';w.color='';refreshStorage();};
 storage.element.onchange=()=>{w.storage=storage.element.value;w.color='';refreshColor();};
 color.element.onchange=()=>{w.color=color.element.value;};
 refreshModels();
 const location=input('City or postal code',w.location||'Toronto, ON');location.element.oninput=()=>w.location=location.element.value;
 const email=input('Notification email',w.email,'email');email.element.oninput=()=>w.email=email.element.value;
 const stores=input('Store IDs (optional, comma-separated)',(w.target_stores||[]).join(', '));stores.element.placeholder='Blank = all nearby stores';stores.element.oninput=()=>w.target_stores=stores.element.value.split(',').map(s=>s.trim()).filter(Boolean);
 grid.append(model.label,storage.label,color.label,location.label,email.label,stores.label);article.append(grid);container.append(article);
 });}
async function unlock(blank){const pass=$('pass').value,token=$('token').value.trim();if(pass.length<12)throw Error('Enter a passphrase of at least 12 characters');if(!token)throw Error('Enter your GitHub token (Contents: read and write)');
 const meta=await getRepoFile('secure_watchlist.json',true);fileSHA=meta?.sha||null;
 if(blank){if(meta)throw Error('An encrypted watchlist already exists. Click Load existing alerts to avoid overwriting it.');watches=[];}
 else if(meta){const raw=atob(meta.content.replace(/\s/g,''));const payload=JSON.parse(raw);watches=await openEnvelope(payload,pass);}
 else {watches=[];status('authStatus','No encrypted watchlist exists. You can add your first phone.');}
 unlocked=true;$('editorPanel').hidden=false;await fetchCatalog();render();}
$('load').onclick=async()=>{try{await unlock(false);if(catalog.length)status('authStatus',`Loaded ${watches.length} alert(s) and ${catalog.length} configurations.`);}catch(e){status('authStatus',e.message,true);}};
$('newList').onclick=async()=>{try{await unlock(true);}catch(e){status('authStatus',e.message,true);}};
$('add').onclick=()=>{if(!catalog.length){status('saveStatus','Catalog not ready. Run the GitHub stock-check workflow once, then reload this page.',true);return;}watches.push({model:'',storage:'',color:'',location:'Toronto, ON',email:'',target_stores:[]});render();};
$('save').onclick=async()=>{try{
 if(!unlocked)throw Error('Unlock your watchlist first');
 if(!catalog.length)throw Error('Apple catalog is unavailable; refusing to save unvalidated variants.');
 const normalized=watches.map((w,i)=>{
 const chosen=catalog.filter(v=>v.model===w.model&&v.storage===w.storage&&v.color===w.color);
 if(chosen.length!==1)throw Error(`Phone ${i+1}: invalid product variant`);
 if(!w.location?.trim())throw Error(`Phone ${i+1}: location is required`);
 if(!/^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$/.test(w.email||''))throw Error(`Phone ${i+1}: valid notification email required`);
 return {model:w.model,storage:w.storage,color:w.color,location:w.location.trim(),email:w.email.trim(),target_stores:w.target_stores||[]};
 });
 if(!normalized.length&&!confirm('Save an empty watchlist? Monitoring will have no alerts.'))return;
 status('saveStatus','Encrypting and saving...');
 const envelope=await seal(normalized,$('pass').value);
 const body={message:'Update encrypted iPhone watchlist',content:b64(enc.encode(JSON.stringify(envelope,null,2)+'\n')),branch:BRANCH};if(fileSHA)body.sha=fileSHA;
 const res=await fetch(API+'secure_watchlist.json',{method:'PUT',headers:{...apiHeaders(true),'Content-Type':'application/json'},body:JSON.stringify(body)});
 if(!res.ok){let reason='';try{reason=(await res.json()).message||'';}catch(_){}throw Error(`GitHub save failed: HTTP ${res.status}. ${reason}`);}
 fileSHA=(await res.json()).content.sha;status('saveStatus',`Saved ${normalized.length} alert(s). The next cron-triggered check will use them.`);
 }catch(e){status('saveStatus',e.message,true);}};
