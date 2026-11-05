/* Mock of the Firebase compat SDK (app + auth + database) for local tests.
   Server data lives in localStorage 'mock-db' so all pages of one browser context share it.
   Write/read permissions mirror database.rules.json. */
(function(){
  const SUPER='dronex666666@gmail.com';
  const LS=k=>{try{return JSON.parse(localStorage.getItem(k)||'null');}catch(e){return null;}};
  const loadDB=()=>LS('mock-db')||{};
  const saveDB=d=>localStorage.setItem('mock-db',JSON.stringify(d));
  const parts=p=>String(p||'').split('/').filter(Boolean);
  const get=(d,p)=>parts(p).reduce((o,k)=>o&&typeof o==='object'?o[k]:undefined,d);
  function put(d,p,v){const ks=parts(p);if(!ks.length)return v;let o=d;for(let i=0;i<ks.length-1;i++){if(!o[ks[i]]||typeof o[ks[i]]!=='object')o[ks[i]]={};o=o[ks[i]];}
    if(v===null||v===undefined)delete o[ks[ks.length-1]];else o[ks[ks.length-1]]=JSON.parse(JSON.stringify(v));return d;}
  const key=e=>String(e||'').toLowerCase().replace(/\./g,',');
  window.__mockLog=[];
  /* ---- auth ---- */
  let user=LS('mock-auth-user');const obs=[];
  function setUser(u){user=u;localStorage.setItem('mock-auth-user',JSON.stringify(u));obs.forEach(f=>f(user));notifyAll();}
  const auth={
    get currentUser(){return user;},
    onAuthStateChanged(f){obs.push(f);setTimeout(()=>f(user),30);return()=>{};},
    getRedirectResult(){return Promise.resolve({user:null});},
    signInWithPopup(){const email=localStorage.getItem('mock-login-as');if(!email)return Promise.reject({code:'auth/popup-closed-by-user',message:'closed'});
      const u={uid:'uid-'+email,email,emailVerified:true};setTimeout(()=>setUser(u),20);return Promise.resolve({user:u});},
    signInWithRedirect(){return Promise.resolve();},
    signOut(){setTimeout(()=>setUser(null),10);return Promise.resolve();},
    signInAnonymously(){window.__mockLog.push('ANON');return Promise.reject({code:'auth/should-not-be-used'});}
  };
  function GoogleAuthProvider(){}GoogleAuthProvider.prototype.setCustomParameters=function(){};
  const authFn=()=>auth;authFn.GoogleAuthProvider=GoogleAuthProvider;
  /* ---- rules ---- */
  const isSuper=()=>!!(user&&user.emailVerified&&user.email.toLowerCase()===SUPER);
  const isAdm=d=>!!(user&&user.emailVerified&&(isSuper()||get(d,'admins/'+key(user.email))===true));
  function canRead(p){const k=parts(p);if(k[0]==='.info')return true;
    if(k[0]==='rooms'&&k[2]==='state')return true;
    if(k[0]==='admins'&&k.length===1)return isSuper();
    if(k[0]==='admins'&&k.length===2)return isSuper()||(user&&key(user.email)===k[1]);
    return false;}
  function canWrite(p,v,d){const k=parts(p);
    if(k[0]==='rooms'&&k[2]==='state'&&k.length>=3)return /^[A-Z0-9]{3,12}$/.test(k[1])&&isAdm(d);
    if(k[0]==='admins')return isSuper()&&(k.length===1||v===null||v===true);
    return false;}
  /* ---- database ---- */
  const listeners=[];
  function snap(v){return{val:()=>v===undefined?null:JSON.parse(JSON.stringify(v)),exists:()=>v!==undefined&&v!==null};}
  function emit(l){if(l.path==='.info/connected')return l.cb(snap(!window.__mockOffline));if(l.path==='.info/serverTimeOffset')return l.cb(snap(0));
    if(!canRead(l.path)){l.err&&l.err({code:'PERMISSION_DENIED',message:'permission_denied'});l.dead=true;return;}
    const v=get(loadDB(),l.path),s=JSON.stringify(v===undefined?null:v);if(s===l.last)return;l.last=s;l.cb(snap(v));}
  function notifyAll(){listeners.filter(l=>!l.dead).forEach(l=>{l.last=l.path.startsWith('.info')?undefined:l.last;emit(l);});}
  window.__mockNotify=notifyAll;
  window.addEventListener('storage',e=>{if(e.key==='mock-db'||e.key==='mock-auth-user'){if(e.key==='mock-auth-user'){user=LS('mock-auth-user');obs.forEach(f=>f(user));}notifyAll();}});
  function write(path,v){if(window.__mockOffline)return new Promise(()=>{});const d=loadDB();
    if(!canWrite(path,v,d)){window.__mockLog.push('DENY '+path);return Promise.reject({code:'PERMISSION_DENIED',message:'permission_denied'});}
    window.__mockLog.push('WRITE '+path);saveDB(put(d,path,v));setTimeout(notifyAll,5);return Promise.resolve();}
  function ref(path){path=parts(path).join('/');return{
    key:parts(path).pop(),
    on(ev,cb,err){const l={path,cb,err,last:undefined};listeners.push(l);setTimeout(()=>emit(l),10);return cb;},
    off(){listeners.forEach(l=>{if(l.path===path)l.dead=true;});},
    once(){return new Promise((res,rej)=>{if(!canRead(path))return rej({code:'PERMISSION_DENIED'});res(snap(get(loadDB(),path)));});},
    set(v){return write(path,v);},
    remove(){return write(path,null);},
    transaction(fn,done){if(window.__mockOffline)return;setTimeout(()=>{const d=loadDB();const cur=get(d,path);const r=fn(cur===undefined?null:JSON.parse(JSON.stringify(cur)));
      if(r===undefined){done&&done(null,false,snap(cur));return;}
      write(path,r).then(()=>done&&done(null,true,snap(r)),e=>done&&done(e,false,snap(cur)));},15);},
  };}
  const db={ref};
  window.firebase={apps:[],initializeApp(c){this.apps.push(c);return{};},auth:authFn,database:()=>db};
})();
