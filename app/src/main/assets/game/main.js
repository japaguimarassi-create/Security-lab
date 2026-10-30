import * as THREE from './vendor/three.module.js';

const $ = (id) => document.getElementById(id);
const WORLD = { w: 28, h: 11, d: 28 };
const grid = new Uint8Array(WORLD.w * WORLD.h * WORLD.d);
const idx = (x, y, z) => x + WORLD.w * (z + WORLD.d * y);
const inside = (x, y, z) => x >= 0 && x < WORLD.w && y >= 0 && y < WORLD.h && z >= 0 && z < WORLD.d;
const blockAt = (x, y, z) => inside(x, y, z) ? grid[idx(x, y, z)] : 0;
const putBlock = (x, y, z, type) => { if (inside(x, y, z)) grid[idx(x, y, z)] = type; };
const state = { started:false, paused:false, resources:0, health:100, extraction:false, weapon:null, preview:null, blueprints:[], history:[], projectiles:[], entities:[], yaw:0, pitch:0, vy:0, player:{x:14,y:4.65,z:23}, bot:null, botHealth:120, botAttackTimer:1, moveX:0, moveY:0, keys:{}, lastTime:0, fps:0, fpsFrames:0, fpsTime:0, toastTimer:0, fly:false, selectedMode:'arena' };

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x90b8c4);
scene.fog = new THREE.Fog(0x90b8c4, 22, 54);
const camera = new THREE.PerspectiveCamera(76, innerWidth / innerHeight, 0.08, 100);
camera.rotation.order = 'YXZ';
const renderer = new THREE.WebGLRenderer({canvas:$('game-canvas'), antialias:false, powerPreference:'high-performance', alpha:false});
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.35));
renderer.setSize(innerWidth, innerHeight, false);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.12;
scene.add(new THREE.HemisphereLight(0xd7f5ff, 0x526272, 1.55));
const sun = new THREE.DirectionalLight(0xfff1cf, 2.1);
sun.position.set(-12, 22, 10);
scene.add(sun);

const matWorld = new THREE.MeshStandardMaterial({vertexColors:true, roughness:0.95, metalness:0.02});
let worldMesh = null;
const colors = [0x000000,0x526a76,0x4f8a61,0x777f86,0x8b6348];
const faceDefs = [
  {n:[1,0,0],v:[[1,0,0],[1,1,0],[1,1,1],[1,0,1]]},
  {n:[-1,0,0],v:[[0,0,1],[0,1,1],[0,1,0],[0,0,0]]},
  {n:[0,1,0],v:[[0,1,1],[1,1,1],[1,1,0],[0,1,0]]},
  {n:[0,-1,0],v:[[0,0,0],[1,0,0],[1,0,1],[0,0,1]]},
  {n:[0,0,1],v:[[1,0,1],[1,1,1],[0,1,1],[0,0,1]]},
  {n:[0,0,-1],v:[[0,0,0],[0,1,0],[1,1,0],[1,0,0]]}
];

function generateWorld() {
  grid.fill(0);
  for (let x=0;x<WORLD.w;x++) for (let z=0;z<WORLD.d;z++) {
    putBlock(x,0,z,1); putBlock(x,1,z, x>3&&z>3&&x<WORLD.w-4&&z<WORLD.d-4 ? 2 : 1);
  }
  for (let x=0;x<WORLD.w;x++) for (let y=2;y<6;y++) { putBlock(x,y,0,1); putBlock(x,y,WORLD.d-1,1); }
  for (let z=0;z<WORLD.d;z++) for (let y=2;y<6;y++) { putBlock(0,y,z,1); putBlock(WORLD.w-1,y,z,1); }
  const pillars=[[5,5],[22,5],[5,21],[22,21],[13,9],[13,18]];
  for (const [x,z] of pillars) for (let y=2;y<7;y++) putBlock(x,y,z,4);
  for (let x=8;x<12;x++) for (let z=12;z<16;z++) putBlock(x,2,z,3);
  for (let x=17;x<21;x++) for (let z=9;z<13;z++) putBlock(x,2,z,3);
  for (let x=10;x<18;x++) putBlock(x,3,6,4);
  for (let x=10;x<18;x++) putBlock(x,3,21,4);
  rebuildWorld();
}

function rebuildWorld() {
  if (worldMesh) { scene.remove(worldMesh); worldMesh.geometry.dispose(); }
  const positions=[], normals=[], vertexColors=[], indices=[];
  for (let y=0;y<WORLD.h;y++) for (let z=0;z<WORLD.d;z++) for (let x=0;x<WORLD.w;x++) {
    const type=blockAt(x,y,z); if (!type) continue;
    for (const face of faceDefs) {
      if (blockAt(x+face.n[0],y+face.n[1],z+face.n[2])) continue;
      const color=new THREE.Color(colors[type]);
      const shade=face.n[1]===1?1.12:face.n[1]===-1?0.68:0.88;
      const base=positions.length/3;
      for (const v of face.v) {
        positions.push(x+v[0],y+v[1],z+v[2]);
        normals.push(...face.n);
        vertexColors.push(color.r*shade,color.g*shade,color.b*shade);
      }
      indices.push(base,base+1,base+2,base,base+2,base+3);
    }
  }
  const geometry=new THREE.BufferGeometry();
  geometry.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));
  geometry.setAttribute('normal',new THREE.Float32BufferAttribute(normals,3));
  geometry.setAttribute('color',new THREE.Float32BufferAttribute(vertexColors,3));
  geometry.setIndex(indices);
  worldMesh=new THREE.Mesh(geometry,matWorld);
  worldMesh.frustumCulled=false;
  scene.add(worldMesh);
}

function floorAt(x,z) {
  const bx=Math.floor(x), bz=Math.floor(z);
  for(let y=WORLD.h-1;y>=0;y--) if(blockAt(bx,y,bz)) return y+1;
  return -20;
}

function material(color, rough=0.65, metal=0.05) { return new THREE.MeshStandardMaterial({color,roughness:rough,metalness:metal}); }
const palette={cyan:0x56dced,blue:0x398fe8,red:0xe15e4f,gold:0xf3bf55,green:0x76cf83,purple:0x9d7ce8,ice:0x91e8ff,fire:0xff743a};
function box(w,h,d,color) { return new THREE.Mesh(new THREE.BoxGeometry(w,h,d),material(color)); }
function sphere(r,color) { return new THREE.Mesh(new THREE.SphereGeometry(r,10,8),material(color)); }
function cyl(rt,rb,h,color,segments=10) { return new THREE.Mesh(new THREE.CylinderGeometry(rt,rb,h,segments),material(color,0.5,0.12)); }

function buildViewWeapon(config) {
  const group=new THREE.Group();
  const main=box(0.19,0.18,0.42,palette[config.element]||0x536878);
  group.add(main);
  const barrelCount=Math.max(1,Math.min(6,config.barrels||1));
  for(let i=0;i<barrelCount;i++){
    const col=(i%3)-1, row=Math.floor(i/3);
    const barrel=cyl(0.035,0.045,0.52,0x222f3a,8);
    barrel.rotation.x=Math.PI/2;
    barrel.position.set(col*0.09,0.12-row*0.09,-0.28);
    group.add(barrel);
  }
  const grip=box(0.11,0.23,0.14,0x283541); grip.position.set(0,-0.16,0.04); grip.rotation.x=-0.22; group.add(grip);
  if(config.body==='rocket') { const shell=box(0.28,0.24,0.46,0x53616a); shell.position.z=0.04; group.add(shell); }
  if(config.element==='electric') { const glow=box(0.23,0.025,0.48,palette.cyan); glow.position.y=0.13; group.add(glow); }
  group.position.set(0.36,-0.29,-0.72);
  group.rotation.y=-0.1;
  camera.add(group);
  return group;
}

function createCreature(kind, color=0x9bb7c4, scale=1) {
  const root=new THREE.Group();
  const body=sphere(0.32,color); body.scale.set(1,0.72,1.3); root.add(body);
  const head=sphere(0.2,color); head.position.set(0,0.14,-0.36); root.add(head);
  const eye1=sphere(0.035,0x101923), eye2=sphere(0.035,0x101923);
  eye1.position.set(-0.08,0.19,-0.51); eye2.position.set(0.08,0.19,-0.51); root.add(eye1,eye2);
  if(kind==='pombo'||kind==='galinha') {
    const beak=cyl(0.01,0.07,0.13,0xe2a64f,5); beak.rotation.x=Math.PI/2; beak.position.set(0,0.1,-0.58); root.add(beak);
    const wing1=box(0.15,0.045,0.3,0xd5dce0), wing2=box(0.15,0.045,0.3,0xd5dce0);
    wing1.position.set(-0.27,0.04,0.03); wing2.position.set(0.27,0.04,0.03); root.add(wing1,wing2);
    root.userData.wings=[wing1,wing2];
  } else {
    for(let i=0;i<4;i++) { const leg=box(0.1,0.32,0.1,color); leg.position.set(i%2?0.19:-0.19,-0.25,i<2?0.2:-0.2); root.add(leg); }
    if(kind==='dragao') { const w1=box(0.55,0.06,0.48,palette.red),w2=box(0.55,0.06,0.48,palette.red); w1.position.set(-0.48,0.15,0.04);w2.position.set(0.48,0.15,0.04);root.add(w1,w2); }
    if(kind==='robo') { const eye=sphere(0.05,palette.cyan);eye.position.set(0,0.18,-0.52);root.add(eye); }
  }
  root.scale.setScalar(scale);
  return root;
}

function makeTower(color=0x657f91) {
  const g=new THREE.Group();
  const base=cyl(0.5,0.6,0.25,0x384a56); base.position.y=0.12; g.add(base);
  const stem=cyl(0.22,0.32,1.15,color); stem.position.y=0.82; g.add(stem);
  const head=box(0.65,0.3,0.65,0x314a5d); head.position.y=1.55; g.add(head);
  const barrel=cyl(0.09,0.12,0.8,0x202e3a);barrel.rotation.x=Math.PI/2;barrel.position.set(0,1.55,-0.56);g.add(barrel);
  return g;
}

function spawnEntity(kind, position, options={}) {
  let object, color=options.element==='fire'?palette.fire:options.element==='ice'?palette.ice:options.element==='electric'?palette.cyan:0x91a8b4;
  if(kind==='torre'||kind==='turret') object=makeTower();
  else if(kind==='carro'||kind==='car') {
    object=new THREE.Group(); const chassis=box(1.1,0.35,1.7,0x4389a8); chassis.position.y=0.45; object.add(chassis);
    const cabin=box(0.8,0.38,0.75,0x254054); cabin.position.set(0,0.8,-0.12); object.add(cabin);
    for(const x of [-0.53,0.53]) for(const z of [-0.5,0.5]) {const w=cyl(0.19,0.19,0.12,0x141b20,9);w.rotation.z=Math.PI/2;w.position.set(x,0.22,z);object.add(w);}
  } else object=createCreature(kind,color,options.giant?1.8:1);
  object.position.copy(position);
  scene.add(object);
  const entity={kind,object,options,life:0,orbit:!!options.orbit,base:position.clone(),angle:Math.random()*Math.PI*2,health:kind==='dragao'?180:60};
  state.entities.push(entity);
  return entity;
}

function addExplosion(position, radius=2, element='fire') {
  const c=new THREE.Mesh(new THREE.SphereGeometry(radius,12,8),new THREE.MeshBasicMaterial({color:palette[element]||palette.fire,transparent:true,opacity:0.38,depthWrite:false}));
  c.position.copy(position); scene.add(c);
  const started=performance.now();
  const tick=()=>{const t=(performance.now()-started)/370;c.scale.setScalar(1+t);c.material.opacity=0.38*(1-t);if(t<1)requestAnimationFrame(tick);else{scene.remove(c);c.geometry.dispose();c.material.dispose();}};tick();
  const center={x:Math.floor(position.x),y:Math.floor(position.y),z:Math.floor(position.z)};
  const removed=[];
  for(let x=center.x-radius;x<=center.x+radius;x++)for(let y=center.y-radius;y<=center.y+radius;y++)for(let z=center.z-radius;z<=center.z+radius;z++){
    const d=Math.hypot(x-center.x,y-center.y,z-center.z);
    if(d<=radius&&blockAt(x,y,z)&&y>1) {removed.push([x,y,z]);}
  }
  for(const [x,y,z] of removed)putBlock(x,y,z,0);
  if(removed.length){rebuildWorld();notify('EXPLOSÃO: '+removed.length+' blocos removidos.');}
  if(state.bot && state.bot.position.distanceTo(position)<radius+1) damageBot(42);
}

const projectiles=[];
function fireProjectile() {
  if(!state.weapon){notify('Você ainda não criou uma arma. Extraia blocos e descreva uma.');return;}
  const cfg=state.weapon;
  const dir=new THREE.Vector3(0,0,-1).applyEuler(camera.rotation).normalize();
  const origin=camera.position.clone().add(dir.clone().multiplyScalar(0.7));
  let object;
  if(cfg.projectile && ['pombo','galinha','lobo','dragao','robo'].includes(cfg.projectile)) object=createCreature(cfg.projectile,cfg.element==='fire'?palette.fire:0xb9c9ce,0.45);
  else {object=sphere(cfg.explosive?0.16:0.08,palette[cfg.element]||palette.gold);}
  object.position.copy(origin);scene.add(object);
  projectiles.push({object,dir,life:0,speed:cfg.explosive?13:22,cfg});
}

function updateProjectiles(dt) {
  for(let i=projectiles.length-1;i>=0;i--){
    const p=projectiles[i];p.life+=dt;p.object.position.addScaledVector(p.dir,p.speed*dt);
    p.object.rotation.y+=dt*5;
    const q=p.object.position;
    if(p.life>2.2||q.y<0||q.x<0||q.z<0||q.x>WORLD.w||q.z>WORLD.d){
      if(p.cfg.explosive)addExplosion(q.clone(),p.cfg.big?3:1.7,p.cfg.element);
      scene.remove(p.object);projectiles.splice(i,1);continue;
    }
    if(state.bot&&q.distanceTo(state.bot.position)<0.8){
      damageBot(p.cfg.damage||20);
      if(p.cfg.explosive)addExplosion(q.clone(),1.8,p.cfg.element);
      scene.remove(p.object);projectiles.splice(i,1);continue;
    }
  }
}

function damageBot(amount) {
  if(!state.bot)return;
  state.botHealth=Math.max(0,state.botHealth-amount);
  if(state.botHealth===0){
    scene.remove(state.bot);state.bot=null;notify('BOT ELIMINADO! Nova unidade em 3 segundos.');
    setTimeout(()=>{if(state.started&&!state.paused&&!state.bot)spawnBot();},3000);
  } else { notify('ACERTO! BOT: '+state.botHealth+' HP'); }
}

function spawnBot() {
  if(state.bot)scene.remove(state.bot);
  state.botHealth=120;state.botAttackTimer=1;
  state.bot=new THREE.Group();
  const torso=box(0.7,1.1,0.4,0x9b4942);torso.position.y=0.9;state.bot.add(torso);
  const head=sphere(0.28,0xb7c1c6);head.position.y=1.65;state.bot.add(head);
  const eye=sphere(0.055,0xff4d4d);eye.position.set(0.1,1.7,-0.24);state.bot.add(eye);
  state.bot.position.set(14,2,4);scene.add(state.bot);
}

function moveBot(dt) {
  if(!state.bot||state.paused)return;
  const dx=state.player.x-state.bot.position.x,dz=state.player.z-state.bot.position.z;
  const distance=Math.hypot(dx,dz);
  if(distance>2.8){state.bot.position.x+=dx/distance*dt*0.7;state.bot.position.z+=dz/distance*dt*0.7;}
  state.botAttackTimer-=dt;
  if(distance<2.25&&state.botAttackTimer<=0){state.health=Math.max(0,state.health-5);state.botAttackTimer=1.15;updateHud();notify(state.health>0?'O BOT ACERTOU!':'VOCÊ FOI DERROTADO. REINICIE A ARENA.');if(state.health===0){state.paused=true;$('pause-panel').classList.remove('hidden');}}
  state.bot.position.y=floorAt(state.bot.position.x,state.bot.position.z);
  state.bot.lookAt(state.player.x,state.bot.position.y+1,state.player.z);
  state.bot.position.y=Math.max(2,state.bot.position.y);
}

function setupArena() {
  for(const entity of state.entities)scene.remove(entity.object);
  for(const p of state.projectiles)scene.remove(p.object);
  state.entities=[];state.projectiles=[];projectiles.length=0;
  state.resources=0;state.health=100;state.weapon=null;state.extraction=false;state.fly=false;
  if(state.weaponView){camera.remove(state.weaponView);state.weaponView=null;}
  generateWorld();
  state.player={x:14,y:4.65,z:23};state.vy=0;state.yaw=0;state.pitch=0;
  camera.position.set(state.player.x,state.player.y,state.player.z);camera.rotation.set(0,0,0);
  spawnBot();updateHud();$('hint').textContent='Ative EXTRAIR, colete blocos e crie sua primeira arma.';
}

function getTargetBlock() {
  const ray=new THREE.Raycaster();ray.setFromCamera(new THREE.Vector2(0,0),camera);
  const hits=ray.intersectObject(worldMesh,false);if(!hits.length)return null;
  const hit=hits[0],n=hit.face.normal.clone().transformDirection(worldMesh.matrixWorld);
  const p=hit.point.clone().addScaledVector(n,-0.025);
  const x=Math.floor(p.x),y=Math.floor(p.y),z=Math.floor(p.z);
  return inside(x,y,z)&&blockAt(x,y,z)?{x,y,z,hit}:null;
}

function mineBlock() {
  const target=getTargetBlock();
  if(!target){notify('Mire em um bloco da arena para extrair.');return;}
  if(target.y<=1){notify('A camada de fundação é protegida.');return;}
  putBlock(target.x,target.y,target.z,0);state.resources+=1;rebuildWorld();updateHud();
  notify('+1 material • '+state.resources+' disponíveis');
}

function fireAction() {
  if(state.paused||!state.started||state.health<=0)return;
  if(state.extraction){mineBlock();return;}
  fireProjectile();
}

function updateHud() {
  $('resources').textContent=state.resources+' MAT';
  $('health').textContent=state.health+' HP';
  $('weapon-label').textContent=state.weapon?state.weapon.name.toUpperCase():'MÃOS VAZIAS';
}

function notify(message) {
  const el=$('toast');el.textContent=message;el.classList.add('show');
  clearTimeout(state.toastTimer);state.toastTimer=setTimeout(()=>el.classList.remove('show'),2100);
}

const WEAPONS=[
  {id:'pistola',words:['pistola','pistol'],kind:'weapon',name:'Pistola'},
  {id:'escopeta',words:['escopeta','shotgun'],kind:'weapon',name:'Escopeta'},
  {id:'rpg',words:['rpg','bazuca','bazooka','lanca foguete','lancador de foguetes'],kind:'weapon',name:'Lançador de foguetes'},
  {id:'fuzil',words:['fuzil','rifle','metralhadora','submetralhadora'],kind:'weapon',name:'Fuzil'},
  {id:'arco',words:['arco e flecha','arco'],kind:'weapon',name:'Arco'},
  {id:'besta',words:['besta','balestra','crossbow'],kind:'weapon',name:'Besta'},
  {id:'espada',words:['espada','sabre'],kind:'weapon',name:'Espada'},
  {id:'lanca',words:['lanca','lança','tridente'],kind:'weapon',name:'Lança'},
  {id:'cajado',words:['cajado','varinha','bastao magico'],kind:'weapon',name:'Cajado'}
];
const CREATURES=[
  {id:'pombo',words:['pombo','pomba','pigeon'],name:'Pombo'},
  {id:'galinha',words:['galinha','frango','chicken'],name:'Galinha'},
  {id:'lobo',words:['lobo','wolf'],name:'Lobo'},
  {id:'tigre',words:['tigre','tiger'],name:'Tigre'},
  {id:'dragao',words:['dragao','dragon'],name:'Dragão'},
  {id:'zumbi',words:['zumbi','zombie'],name:'Zumbi'},
  {id:'aranha',words:['aranha','spider'],name:'Aranha'},
  {id:'elefante',words:['elefante','elephant'],name:'Elefante'},
  {id:'robo',words:['robo','robot','androide'],name:'Robô'},
  {id:'golem',words:['golem'],name:'Golem'}
];
const OBJECTS=[
  {id:'torre',words:['torre','torreta','turret'],kind:'object',name:'Torre automática'},
  {id:'escudo',words:['escudo','shield'],kind:'object',name:'Escudo'},
  {id:'parede',words:['parede','muro','wall'],kind:'object',name:'Parede móvel'},
  {id:'carro',words:['carro','veiculo','veículo','car'],kind:'vehicle',name:'Veículo'},
  {id:'drone',words:['drone'],kind:'vehicle',name:'Drone'},
  {id:'bomba',words:['bomba','mina','bomb'],kind:'object',name:'Bomba'},
  {id:'armadura',words:['armadura','armor'],kind:'armor',name:'Armadura'},
  {id:'asa',words:['asas','asa'],kind:'ability',name:'Asas'}
];
const ELEMENTS=[
  {id:'fire',words:['fogo','flamejante','incendiario','incendiária','explosivo','explosiva','explodir','explosao','explosão'],label:'Explosivo / fogo'},
  {id:'ice',words:['gelo','congelante','gelado','frio'],label:'Gelo'},
  {id:'electric',words:['eletrico','eletrica','eletricos','eletricas','raio','eletricidade'],label:'Elétrico'},
  {id:'poison',words:['veneno','venenoso','toxica','toxica'],label:'Veneno'}
];

function normalize(text) { return String(text||'').toLocaleLowerCase('pt-BR').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9\s]/g,' ').replace(/\s+/g,' ').trim(); }
function hasPhrase(text,phrase) {
  const p=normalize(phrase);
  return p.length>0 && (' '+text+' ').includes(' '+p+' ');
}
function firstMatch(list,text) {
  let best=null,bestIndex=Infinity;
  for(const item of list) for(const word of item.words) {
    const phrase=normalize(word);const index=(' '+text+' ').indexOf(' '+phrase+' ');
    if(index>=0&&index<bestIndex){best=item;bestIndex=index;}
  }
  return best;
}
function numberFrom(text) {
  const numeric=text.match(/\b(\d{1,2})\b/);if(numeric)return Math.max(1,Math.min(12,Number(numeric[1])));
  const words={um:1,uma:1,dois:2,duas:2,tres:3,quatro:4,cinco:5,seis:6,sete:7,oito:8,nove:9,dez:10};
  for(const [word,n] of Object.entries(words))if(hasPhrase(text,word))return n;
  return 1;
}
function parseCommand(raw) {
  const text=normalize(raw);
  if(!text)return {error:'Digite ou fale uma ideia primeiro.'};
  if(hasPhrase(text,'voar')||hasPhrase(text,'voo')||hasPhrase(text,'voar livre'))return {id:'voar',kind:'ability',name:'Voo',details:'Habilidade temporária de voo',cost:4,element:'cyan',raw};
  if(hasPhrase(text,'super pulo')||hasPhrase(text,'pulo gigante'))return {id:'superpulo',kind:'ability',name:'Super pulo',details:'Salto com impulso ampliado',cost:3,element:'electric',raw};
  const all=[...WEAPONS,...OBJECTS];
  let primary=firstMatch(all,text);
  let creature=firstMatch(CREATURES,text);
  if(!primary&&creature){primary={id:creature.id,kind:'creature',name:creature.name};}
  if(!primary&&hasPhrase(text,'criar'))return {error:'Diga o que deseja criar: arma, criatura, torre, veículo, armadura ou habilidade.'};
  if(!primary)return {error:'Não reconheci o objeto principal. Tente um nome específico, como pistola, dragão, torre, carro ou armadura.'};
  let count=numberFrom(text);
  const barrelsMatch=text.match(/(\d{1,2}|um|uma|dois|duas|tres|quatro|cinco|seis) (cano|canos|boca|bocas|disparo|disparos|carga|cargas)/);
  const barrels=barrelsMatch?Math.max(1,Math.min(6,numberFrom(barrelsMatch[0]))):1;
  const element=firstMatch(ELEMENTS,text);
  const projectile=creature && (hasPhrase(text,'atira')||hasPhrase(text,'lanca')||hasPhrase(text,'dispara')||hasPhrase(text,'solta')) ? creature.id : null;
  const orbit=hasPhrase(text,'orbita')||hasPhrase(text,'orbitam')||hasPhrase(text,'ao meu redor')||hasPhrase(text,'me acompanha');
  const giant=hasPhrase(text,'gigante')||hasPhrase(text,'enorme');
  const homing=hasPhrase(text,'teleguiado')||hasPhrase(text,'persegue')||hasPhrase(text,'segue');
  const explosive=!!element&&element.id==='fire'||hasPhrase(text,'explosivo')||hasPhrase(text,'explosiva');
  const ammo=Math.max(1,Math.min(20,numberFrom(text)));
  const body=hasPhrase(text,'corpo de bazuca')||hasPhrase(text,'corpo de foguete')?'rocket':'standard';
  let cost=primary.kind==='weapon'?4:primary.kind==='creature'?3:primary.kind==='vehicle'?7:primary.kind==='armor'?6:4;
  cost+=Math.max(0,barrels-1)+Math.max(0,count-1);
  if(element)cost+=2;if(giant)cost+=3;if(projectile)cost+=2;
  if(primary.id==='rpg')cost+=2;
  cost=Math.min(30,cost);
  const typeName=primary.name||primary.id;
  const modifiers=[barrels>1?barrels+' canos':null,element?element.label:null,projectile?'dispara '+creature.name:null,giant?'tamanho gigante':null,homing?'teleguiado':null,orbit?'orbital':null].filter(Boolean);
  return {id:primary.id,kind:primary.kind||'creature',name:(count>1?count+'x ':'')+typeName,details:modifiers.length?modifiers.join(' • '):'Modelo básico com comportamento funcional',cost,barrels,element:element?.id||'cyan',projectile,orbit,giant,homing,explosive,ammo,body,count,damage:primary.id==='rpg'?52:primary.id==='espada'?28:primary.id==='escopeta'?30:20,raw};
}

function showPreview(parsed) {
  state.preview=parsed;
  $('preview-name').textContent=parsed.name;
  $('preview-details').textContent=parsed.details;
  $('preview-cost').textContent=parsed.cost+' materiais';
  $('preview').classList.remove('hidden');
  $('confirm-craft').disabled=state.resources<parsed.cost;
  $('confirm-craft').textContent=state.resources<parsed.cost?'FALTAM '+(parsed.cost-state.resources)+' MATERIAIS':'CRIAR AGORA';
  $('confirm-craft').style.opacity=state.resources<parsed.cost?'.5':'1';
}

function submitCommand(raw) {
  const parsed=parseCommand(raw);
  state.history.unshift({raw,ok:!parsed.error});
  state.history=state.history.slice(0,30);
  localStorage.setItem('vf_history',JSON.stringify(state.history));
  if(parsed.error){notify(parsed.error);$('voice-status').textContent=parsed.error;return;}
  $('voice-status').textContent='Pedido entendido. Confira a prévia e confirme para construir.';
  showPreview(parsed);
}

function confirmCraft() {
  const cfg=state.preview;if(!cfg)return;
  if(state.resources<cfg.cost){notify('Materiais insuficientes. Extraia mais blocos.');return;}
  state.resources-=cfg.cost;
  if(cfg.kind==='weapon') {
    state.weapon=cfg;
    if(state.weaponView)camera.remove(state.weaponView);
    state.weaponView=buildViewWeapon(cfg);
    notify(cfg.name+' criada e equipada.');
  } else if(cfg.kind==='ability') {
    if(cfg.id==='voar'){state.fly=true;notify('Voo ativado!');}
    else {state.player.y+=2.6;state.vy=6;notify('Super pulo ativado!');}
  } else if(cfg.id==='torre') {
    const p=camera.position.clone().add(new THREE.Vector3(0,0,-4).applyEuler(camera.rotation));spawnEntity('torre',new THREE.Vector3(Math.round(p.x),Math.max(2,floorAt(p.x,p.z)),Math.round(p.z)),cfg);notify('Torre colocada na arena.');
  } else if(cfg.kind==='armor'||cfg.id==='escudo') {
    state.health=Math.min(100,state.health+cfg.cost*5);notify(cfg.name+' equipada. Defesa reforçada.');
  } else {
    const base=camera.position.clone().add(new THREE.Vector3(0,0,-3).applyEuler(camera.rotation));
    for(let i=0;i<Math.min(cfg.count||1,5);i++) {
      const pos=base.clone().add(new THREE.Vector3((i-(Math.min(cfg.count||1,5)-1)/2)*1.2,0,0));
      spawnEntity(cfg.id,pos,cfg);
    }
    if(cfg.kind==='vehicle'&&cfg.id==='carro')notify('Veículo montado. Use o botão de interação para entrar (em desenvolvimento).');
    else notify(cfg.name+' materializado na arena.');
  }
  state.blueprints.unshift(cfg);
  state.blueprints=state.blueprints.slice(0,20);
  localStorage.setItem('vf_blueprints',JSON.stringify(state.blueprints));
  updateHud();renderInventory();state.preview=null;$('preview').classList.add('hidden');$('command-panel').classList.add('hidden');
}

function renderInventory() {
  const bp=$('blueprint-list');bp.innerHTML='';
  if(!state.blueprints.length)bp.innerHTML='<div class="empty-state">Nenhum projeto salvo ainda. Crie sua primeira invenção.</div>';
  state.blueprints.forEach((item,i)=>{
    const row=document.createElement('div');row.className='blueprint-item';
    const label=document.createElement('span');label.textContent=item.name+' · '+item.cost+' MAT';
    const btn=document.createElement('button');btn.textContent='REUTILIZAR';btn.addEventListener('click',()=>{showPreview(item);$('inventory-panel').classList.add('hidden');$('command-panel').classList.remove('hidden');});
    row.append(label,btn);bp.append(row);
  });
  const history=$('command-history');history.innerHTML='';
  if(!state.history.length)history.innerHTML='<div class="empty-state">Seus últimos comandos aparecerão aqui.</div>';
  state.history.slice(0,10).forEach(item=>{const row=document.createElement('div');row.className='history-item';row.textContent=(item.ok?'✓ ':'• ')+item.raw;history.append(row);});
}

function openPanel(id) {$('command-panel').classList.toggle('hidden',id!=='command-panel');$('pause-panel').classList.toggle('hidden',id!=='pause-panel');$('tutorial-panel').classList.toggle('hidden',id!=='tutorial-panel');$('inventory-panel').classList.toggle('hidden',id!=='inventory-panel');}
function openCommand() {openPanel('command-panel');$('preview').classList.add('hidden');$('command-input').focus();}
function togglePause() {state.paused=!state.paused;$('pause-panel').classList.toggle('hidden',!state.paused);}
window.showPauseMenu=()=>{if(state.started){state.paused=true;$('pause-panel').classList.remove('hidden');}};

function setupControls() {
  const pad=$('move-pad'),knob=$('stick-knob');let stickPointer=null;
  const updateStick=(event)=>{
    const rect=pad.getBoundingClientRect();const cx=rect.left+rect.width/2,cy=rect.top+rect.height/2;
    let dx=event.clientX-cx,dy=event.clientY-cy;const max=34;const len=Math.hypot(dx,dy);
    if(len>max){dx=dx/len*max;dy=dy/len*max;}
    knob.style.transform='translate('+dx+'px,'+dy+'px)';
    state.moveX=dx/max;state.moveY=dy/max;
  };
  pad.addEventListener('pointerdown',e=>{stickPointer=e.pointerId;pad.setPointerCapture(e.pointerId);updateStick(e);});
  pad.addEventListener('pointermove',e=>{if(e.pointerId===stickPointer)updateStick(e);});
  const endStick=e=>{if(e.pointerId===stickPointer){stickPointer=null;state.moveX=0;state.moveY=0;knob.style.transform='translate(0,0)';}};
  pad.addEventListener('pointerup',endStick);pad.addEventListener('pointercancel',endStick);
  let lookPointer=null,lastX=0,lastY=0;
  const canvas=$('game-canvas');
  canvas.addEventListener('pointerdown',e=>{if(e.pointerType==='mouse')return;lookPointer=e.pointerId;lastX=e.clientX;lastY=e.clientY;canvas.setPointerCapture(e.pointerId);});
  canvas.addEventListener('pointermove',e=>{if(e.pointerId!==lookPointer)return;const dx=e.clientX-lastX,dy=e.clientY-lastY;lastX=e.clientX;lastY=e.clientY;state.yaw-=dx*0.0042;state.pitch=Math.max(-1.25,Math.min(1.25,state.pitch-dy*0.0035));});
  const endLook=e=>{if(e.pointerId===lookPointer)lookPointer=null;};
  canvas.addEventListener('pointerup',endLook);canvas.addEventListener('pointercancel',endLook);
  $('extract').addEventListener('click',()=>{state.extraction=!state.extraction;$('extract').classList.toggle('active',state.extraction);$('hint').textContent=state.extraction?'MODO EXTRAÇÃO: mire em blocos e toque na arena.':'Modo combate: toque em DISPARAR para usar sua criação.';notify(state.extraction?'EXTRAÇÃO ATIVADA':'COMBATE ATIVADO');});
  $('voice').addEventListener('click',()=>{openCommand();$('voice-status').textContent='Solicitando reconhecimento de voz…';if(window.AndroidBridge)window.AndroidBridge.startVoice();else notify('Reconhecimento de voz disponível apenas no APK Android.');});
  $('fire').addEventListener('pointerdown',e=>{e.preventDefault();fireAction();});
  $('jump').addEventListener('click',()=>{if(state.fly){state.player.y+=1.2;}else if(Math.abs(state.vy)<0.1)state.vy=6.4;});
  $('text-open').addEventListener('click',openCommand);
  $('inventory-open').addEventListener('click',()=>{renderInventory();openPanel('inventory-panel');});
  $('tutorial-open').addEventListener('click',()=>openPanel('tutorial-panel'));
  $('pause').addEventListener('click',togglePause);
  $('resume').addEventListener('click',()=>{state.paused=false;$('pause-panel').classList.add('hidden');});
  $('reset').addEventListener('click',()=>{setupArena();state.paused=false;$('pause-panel').classList.add('hidden');notify('Arena reiniciada.');});
  $('pause-help').addEventListener('click',()=>{$('pause-panel').classList.add('hidden');openPanel('tutorial-panel');});
  document.querySelectorAll('[data-close]').forEach(btn=>btn.addEventListener('click',()=>$(btn.dataset.close).classList.add('hidden')));
  $('start').addEventListener('click',()=>{state.started=true;$('title-screen').classList.add('hidden');$('hud').classList.remove('hidden');$('tutorial-panel').classList.remove('hidden');setupArena();});
  $('command-form').addEventListener('submit',e=>{e.preventDefault();submitCommand($('command-input').value);});
  $('confirm-craft').addEventListener('click',confirmCraft);
  $('cancel-craft').addEventListener('click',()=>{$('preview').classList.add('hidden');state.preview=null;});
  document.querySelectorAll('.sample').forEach(btn=>btn.addEventListener('click',()=>{$('command-input').value=btn.textContent;submitCommand(btn.textContent);}));
  $('game-canvas').addEventListener('click',()=>{if(state.started&&!state.paused)fireAction();});
  window.addEventListener('keydown',e=>{state.keys[e.key.toLowerCase()]=true;if(e.key.toLowerCase()==='t')openCommand();if(e.key==='Escape')togglePause();if(e.key===' '&&state.started)state.vy=6.2;if(e.key.toLowerCase()==='e')state.extraction=!state.extraction;});
  window.addEventListener('keyup',e=>{state.keys[e.key.toLowerCase()]=false;});
  window.addEventListener('resize',()=>{camera.aspect=innerWidth/innerHeight;camera.updateProjectionMatrix();renderer.setSize(innerWidth,innerHeight,false);renderer.setPixelRatio(Math.min(devicePixelRatio||1,1.35));});
}

window.onNativeSpeechStatus=(message)=>{$('voice-status').textContent=message;};
window.onNativeSpeechPartial=(text)=>{$('command-input').value=text;$('voice-status').textContent='Reconhecendo: '+text;};
window.onNativeSpeechResult=(text)=>{$('command-input').value=text;$('voice-status').textContent='Frase recebida. Revise e toque em ANALISAR PEDIDO.';notify('Voz convertida em texto. Confira antes de criar.');};
window.onNativeSpeechError=(message)=>{$('voice-status').textContent=message;notify(message);};

function update(dt) {
  if(state.paused||!state.started)return;
  const forward=(state.keys.w||state.keys.arrowup?1:0)-(state.keys.s||state.keys.arrowdown?1:0)-state.moveY;
  const side=(state.keys.d||state.keys.arrowright?1:0)-(state.keys.a||state.keys.arrowleft?1:0)+state.moveX;
  const input=new THREE.Vector3(side,0,forward);
  if(input.lengthSq()>1)input.normalize();
  input.applyAxisAngle(new THREE.Vector3(0,1,0),state.yaw);
  const speed=state.keys.shift?7.2:4.4;
  const nx=THREE.MathUtils.clamp(state.player.x+input.x*speed*dt,1.3,WORLD.w-2.3);
  const nz=THREE.MathUtils.clamp(state.player.z-input.z*speed*dt,1.3,WORLD.d-2.3);
  if(!blockAt(Math.floor(nx),Math.floor(state.player.y-1.1),Math.floor(state.player.z)))state.player.x=nx;
  if(!blockAt(Math.floor(state.player.x),Math.floor(state.player.y-1.1),Math.floor(nz)))state.player.z=nz;
  if(!state.fly){state.vy-=16*dt;state.player.y+=state.vy*dt;const floor=floorAt(state.player.x,state.player.z)+1.65;if(state.player.y<floor){state.player.y=floor;state.vy=0;}}
  else {state.player.y+=((state.keys[' ']?1:0)-(state.keys.c?1:0))*speed*dt;}
  camera.position.set(state.player.x,state.player.y,state.player.z);
  camera.rotation.set(state.pitch,state.yaw,0);
  updateProjectiles(dt);moveBot(dt);
  for(const entity of state.entities){entity.life+=dt;if(entity.orbit){entity.angle+=dt*1.6;entity.object.position.set(entity.base.x+Math.cos(entity.angle)*1.5,entity.base.y+0.6+Math.sin(entity.angle*2)*0.25,entity.base.z+Math.sin(entity.angle)*1.5);entity.object.rotation.y=-entity.angle;}}
}

function loop(now) {
  requestAnimationFrame(loop);
  const dt=Math.min((now-state.lastTime)/1000||0,0.05);state.lastTime=now;
  update(dt);renderer.render(scene,camera);
  state.fpsFrames++;state.fpsTime+=dt;
  if(state.fpsTime>=0.7){$('fps').textContent=Math.round(state.fpsFrames/state.fpsTime)+' FPS';state.fpsFrames=0;state.fpsTime=0;}
}

try {
  const saved=JSON.parse(localStorage.getItem('vf_blueprints')||'[]');if(Array.isArray(saved))state.blueprints=saved;
  const hist=JSON.parse(localStorage.getItem('vf_history')||'[]');if(Array.isArray(hist))state.history=hist;
} catch(e) {}
setupControls();
setupArena();
requestAnimationFrame(loop);
