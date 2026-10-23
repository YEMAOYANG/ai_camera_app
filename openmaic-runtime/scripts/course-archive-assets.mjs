#!/usr/bin/env node
/** Read only the assets referenced by one authoritative Native course capture. */
import fs from 'node:fs/promises';
import {constants as fsConstants} from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import https from 'node:https';
import {lookup as dnsLookup} from 'node:dns';
import {isIP} from 'node:net';
import {createRequire} from 'node:module';
import {fileURLToPath,pathToFileURL} from 'node:url';

const ROOT=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const NATIVE=path.join(ROOT,'openmaic-runtime/.runtime/OpenMAIC');
const require=createRequire(path.join(NATIVE,'package.json'));
const {enumerateAssetManifest}=await import(pathToFileURL(path.join(NATIVE,'packages/@openmaic/dsl/dist/index.js')));
const {DOMParser}=require('linkedom');
const parseSrcset=require('parse-srcset');
const parseCssValue=require('postcss-value-parser');
const ts=require('typescript');
const MAX_BYTES=768*1024**2,MAX_TOTAL=4*1024**3,MAX_INPUT=128*1024**2;
const sha=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
const THREE_BASE='https://unpkg.com/three@0.160.0/';
const THREE_ENTRIES=new Set(['build/three.module.js','examples/jsm/controls/OrbitControls.js']);
// Official npm three@0.160.0 tarball integrity and the exact inert file pins.
// sha512-DLU8lc0zNIPkM7rH5/e1Ks1Z8tWCGRq6g8mPowdDJpw1CFBJMU7UoJjC6PefXW7z//SSl0b2+GCw14LB+uDhng==
const THREE_FILES={"build/three.module.js":[1272972,"76dea8151bc9352aef3528b4262e249b2604f62543828328db978d060d61a495"],"examples/jsm/controls/OrbitControls.js":[29868,"5a44a9e86a2a0fb11933eed69bc2cd33c76a496854c1aed6ed776efa87d7b064"],"LICENSE":[1081,"852e0e8699169bf9f6fdc6bda3e682d078dcbc738b5d33e74df594721bff271d"],"package.json":[3997,"f0392af130d7a636b1ebf086509ae2d71d69a3d89e93b2e081c1b556b94dc266"]};
const KATEX_BASE='https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/';
const KATEX_ENTRIES=new Set(['katex.min.css','katex.min.js','contrib/auto-render.min.js']);
// Official npm katex@0.16.9 tarball, verified before deriving these file pins:
// https://registry.npmjs.org/katex/-/katex-0.16.9.tgz
// sha512-fsSYjWS0EEOwvy81j3vRA8TEAhQhKiqO+FQaKWp0m39qwOzHVBgAUBIXWj1pB+O2W3fIpNa6Y9KSKCVbfPhyAQ==
const KATEX_FILES={
 "contrib/auto-render.min.js":[3478,"9cb8dacfc086c2966c9ec4ba54f4a2dc43b7cbe2b33cec1a2743d886c7fb47a7"],
 "fonts/KaTeX_AMS-Regular.ttf":[63632,"68534840bcfdd2bffb6f0e8deb48684dd01e7f04ea2813267577afb906de1d13"],
 "fonts/KaTeX_AMS-Regular.woff":[33516,"30da91e84c893f875e252689faebdc590b2871145e8adc7f9a9d4dbd8ce0b251"],
 "fonts/KaTeX_AMS-Regular.woff2":[28076,"0cdd387c9590a1a9f9794560022dbb59654a7d86f187aa0c81495ad42d3a7308"],
 "fonts/KaTeX_Caligraphic-Bold.ttf":[12368,"07d8e303ce4fc12b4bb54f1004170dd190a1f3db45d400fe68060df3e0897268"],
 "fonts/KaTeX_Caligraphic-Bold.woff":[7716,"1ae6bd7475590e97e7f145a89e09ccde322f7a6bc0b91607b1c8b8ee28290fed"],
 "fonts/KaTeX_Caligraphic-Bold.woff2":[6912,"de7701e42cf1f4cf0b766c03fb27977207eee2f4fd5d76fa82188406da43ea4c"],
 "fonts/KaTeX_Caligraphic-Regular.ttf":[12344,"ed0b74372feefcbb9c0666b2e210da37b7e49fa7fbbf3eeb11db5f693dacfbb7"],
 "fonts/KaTeX_Caligraphic-Regular.woff":[7656,"3398dd02302557a793f2863f88e02d96ce10df2abffa07c8e9fa90775116e65c"],
 "fonts/KaTeX_Caligraphic-Regular.woff2":[6908,"5d53e70ad607c2352162dec9e0923fb54ecdafaccbf604cd8dcf7d00facb989b"],
 "fonts/KaTeX_Fraktur-Bold.ttf":[19584,"9163df9c7122432e6495b4229fa9071cf9ae86a758ae5efc4924ec2e1a6dbce1"],
 "fonts/KaTeX_Fraktur-Bold.woff":[13296,"9be7ceb88004ab8ad124082246fbfcca4091e36385d4ec6ed1df67375dad50fb"],
 "fonts/KaTeX_Fraktur-Bold.woff2":[11348,"74444efd593c005e3f4573b44524704c0af0a937fe911cca9e94068d0d140d3f"],
 "fonts/KaTeX_Fraktur-Regular.ttf":[19572,"1e6f9579e90e2cac37f8f60a597c436e075c114385652b7cbeb0dec0421291b3"],
 "fonts/KaTeX_Fraktur-Regular.woff":[13208,"5e28753be717dac97f559f49bc10be9cf3c124ddcabda6659d11cb68febc6463"],
 "fonts/KaTeX_Fraktur-Regular.woff2":[11316,"51814d270d06ff0255dba0799994fa4d8c84d11f09951d47595f4abb1f3602dc"],
 "fonts/KaTeX_Main-Bold.ttf":[51336,"138ac28d1663b3037e9c5f52371fa5c63d8324f4a38d22cd573e6ea3a3fd0cf8"],
 "fonts/KaTeX_Main-Bold.woff":[29912,"c76c5d696297d51b9cb1639c7da4334f0e7dec81b42b11213b5e25ef671bb822"],
 "fonts/KaTeX_Main-Bold.woff2":[25324,"0f60d1b897938ec918c8ce073092411baf9438f6739465693ff18b0f9d20b021"],
 "fonts/KaTeX_Main-BoldItalic.ttf":[32968,"70ee1f64a20f2048c21940ef46d0144fd215baa953ca69afd1e31e98544f708f"],
 "fonts/KaTeX_Main-BoldItalic.woff":[19412,"a6f7ec0d846ac7ad975adb8959c37ed49b94acbc4ae436db9ce9e20287e4a64c"],
 "fonts/KaTeX_Main-BoldItalic.woff2":[16780,"99cd42a3c072d918f2f44984a807cf7aa16e13545fd0875fc07c6c65f99e715b"],
 "fonts/KaTeX_Main-Italic.ttf":[33580,"0d85ae7cc30f23790a7f1a58c4a112fdca8aae769b6ba11429af1d98b1b6cb3a"],
 "fonts/KaTeX_Main-Italic.woff":[19676,"f1d6ef86f3b11a528bd5185199bd2443ecb2b0dead96d88674b5a2c12be24bdf"],
 "fonts/KaTeX_Main-Italic.woff2":[16988,"97479ca6cce906abc961ecac96faa5f9ca2e61b8e7670d475826bcdee9a7c267"],
 "fonts/KaTeX_Main-Regular.ttf":[53580,"d0332f52868370fd83ae7fa46470f90c8f2eab2fcf12bc4f88080b340c95a830"],
 "fonts/KaTeX_Main-Regular.woff":[30772,"c6368d87e8a1a3a5d337623d83d8dc4b868f242a9ad476237d6f8d1e0f168cdc"],
 "fonts/KaTeX_Main-Regular.woff2":[26272,"c2342cd8b869e01752a9321dc17213fc40d4d04c79688c1d43f2cf316abd7866"],
 "fonts/KaTeX_Math-BoldItalic.ttf":[31196,"f9377ab0271cda59af24bcffbd46a4d0c8a3572ffafdbb38de2ad5ea7b0d5ee5"],
 "fonts/KaTeX_Math-BoldItalic.woff":[18668,"850c0af5c2238497febaf5e461d880bf458c341f42f4f330f1b1ab5698b1998e"],
 "fonts/KaTeX_Math-BoldItalic.woff2":[16400,"dc47344dbb6cb5b655c8460d561f4df5f501b90c804ad3c6cec65fe322351ab1"],
 "fonts/KaTeX_Math-Italic.ttf":[31308,"08ce98e51b04d58945a301e639e02b6998af29fdfd61a7b8afdd07bbfc479d4a"],
 "fonts/KaTeX_Math-Italic.woff":[18748,"8a8d244581371912b8f3f5a23e2437cb2a59cd9bcaebb0346e722c05737a2571"],
 "fonts/KaTeX_Math-Italic.woff2":[16440,"7af58c5ec8f132a2ddde9027c6d7814decce4d3b822a11192a42a20e2e973264"],
 "fonts/KaTeX_SansSerif-Bold.ttf":[24504,"1ece03f79f95277d57dc7f6b435a74e1379b0d46104a8530286b60ff49369ea0"],
 "fonts/KaTeX_SansSerif-Bold.woff":[14408,"ece03cfd83e22c212cdef66feb8442d25a083beb988db3f1883f3f9738d750ba"],
 "fonts/KaTeX_SansSerif-Bold.woff2":[12216,"e99ae51144bf1232efcc1bfe5add36262c6866b0faab24fa75740e1b98577a62"],
 "fonts/KaTeX_SansSerif-Italic.ttf":[22364,"3931dd81faed86ba021bb2bbdc36f5bed9a38d6b4f4077aca59b265aa1b02083"],
 "fonts/KaTeX_SansSerif-Italic.woff":[14112,"91ee67500cc0129aa0ace3ac5c61ff1692102f0f31d02b69347fba35dcb75bf2"],
 "fonts/KaTeX_SansSerif-Italic.woff2":[12028,"00b26ac825e2095056396e0553b8ac26d3f8ad158c3826e28b4c45b385c4714a"],
 "fonts/KaTeX_SansSerif-Regular.ttf":[19436,"f36ea897e19f4a2e571d1e900e4e3710e438deb05a842486045ba0a3e616a4ad"],
 "fonts/KaTeX_SansSerif-Regular.woff":[12316,"11e4dc8a6471ff6d6ee561d53d10fde8f7489e798257ff449c5d37c197435605"],
 "fonts/KaTeX_SansSerif-Regular.woff2":[10344,"68e8c73ef42afd3ccec58bf0fba302cce448938e7fc020a5e31f8a952eee1342"],
 "fonts/KaTeX_Script-Regular.ttf":[16648,"1c67f068fea8bb09bf099c088b1cf64bd27516a6e07f4684344873564bb66a67"],
 "fonts/KaTeX_Script-Regular.woff":[10588,"d96cdf2b3bdd4d64a8fd5f74a4c467f123a8a73931cd435889f08ffaf9bf947a"],
 "fonts/KaTeX_Script-Regular.woff2":[9644,"036d4e95149b69ff9bcc0cd55771efeb25ffa3947293e69acd78d5ac328c684b"],
 "fonts/KaTeX_Size1-Regular.ttf":[12228,"95b6d2f1a50173bfedb8c63e1d1c99b10427d0a4df4201cb44513b226951a22b"],
 "fonts/KaTeX_Size1-Regular.woff":[6496,"c943cc986384f59e86bea5fd7dc50a9c4dfe567a7c05eb40d6790720dead97c9"],
 "fonts/KaTeX_Size1-Regular.woff2":[5468,"6b47c40166b6dbe21a5dfca7718413f2147fd2399be1ba605d8ad39cedf25dfe"],
 "fonts/KaTeX_Size2-Regular.ttf":[11508,"a6b2099fb555c60e3a0db3a08842ebf1d732c6eb4e4bf44913613bed4fc4e39b"],
 "fonts/KaTeX_Size2-Regular.woff":[6188,"2014c523c3210bcc166648c4d4cc57f05b747df07a24277bf71c51e67dc79e3d"],
 "fonts/KaTeX_Size2-Regular.woff2":[5208,"d04c54219f9eaec6d4d4fd42dfb28785975a4794d6b2fc71e566b9cd6db842dd"],
 "fonts/KaTeX_Size3-Regular.ttf":[7588,"500e04d54f0d51666332c9d2089aa803be22aa878eca539e59fa53c6e522b082"],
 "fonts/KaTeX_Size3-Regular.woff":[4420,"6ab6b62e9b62dae2c00dd90f791bd10950be0ecc3490d7d6045f51c2e8fe0949"],
 "fonts/KaTeX_Size3-Regular.woff2":[3624,"73d591271b1604960cb10bb90fee021670af7297017e0e98480b332d11f51995"],
 "fonts/KaTeX_Size4-Regular.ttf":[10364,"c647367d1dd4e162468717d020e1fc0f1dc5c26ebfdffbe55261713bf88c5877"],
 "fonts/KaTeX_Size4-Regular.woff":[5980,"99f9c6750b489c9462bf04900bd3f939df9b829339daaaaa99ef5495cdddea58"],
 "fonts/KaTeX_Size4-Regular.woff2":[4928,"a4af7d414440a1c1790825cfb700cf9cf43b0f2c4b04f0ebc523011ad9853ec0"],
 "fonts/KaTeX_Typewriter-Regular.ttf":[27556,"f01f3e87d9c6a61c0c081ceb577abd864eb00a612f7ac1620dd6915fad2ef5aa"],
 "fonts/KaTeX_Typewriter-Regular.woff":[16028,"e14fed02b1aba7ce9f5afd5844b5d0321b22351febc720e0de8b8723527609f7"],
 "fonts/KaTeX_Typewriter-Regular.woff2":[13568,"71d517d67827787cfabdf186914cc3358eda539e37931941f2b2fd4a21f68c0b"],
 "katex.min.css":[23196,"505d5f829022bb7b4f24dfee0aa1141cd7bba67afe411d1240335f820960b5c3"],
 "katex.min.js":[277038,"dc84b296ec3e884de093158f760fd9d45b6c7abe58b5381557f4e138f46a58ae"],
};
export function canonical(value){
 const sorted=x=>Array.isArray(x)?x.map(sorted):x&&typeof x==='object'?Object.fromEntries(Object.entries(x).sort(([a],[b])=>a<b?-1:a>b?1:0).map(([k,v])=>[k,sorted(v)])):x;
 return JSON.stringify(sorted(value));
}
function classroom(ref){
 if(typeof ref!=='string')return false;
 let logical=ref;
 if(/^https?:/i.test(ref)){
  try{const url=new URL(ref);if(!['localhost','127.0.0.1','[::1]'].includes(url.hostname)||url.username||url.password||url.search||url.hash)return false;logical=url.pathname;}
  catch{return false;}
 }
 return /^\/api\/classroom-media\/[A-Za-z0-9_-]+\/(?:audio|media)\/[A-Za-z0-9_.-]+$/.test(logical)&&!logical.includes('..');
}
const inline=ref=>typeof ref==='string' && /^(?:#|data:(?:(?:image|audio|video|font)\/[a-z0-9.+-]+|application\/(?:font[a-z0-9.+-]*|x-font[a-z0-9.+-]*|vnd.ms-fontobject))[;,])/i.test(ref);
const plain=ref=>typeof ref==='string' && ref && !/[\x00-\x1f\x7f-\x9f]/.test(ref);
const NAMESPACES=new Set(['http://www.w3.org/2000/svg','http://www.w3.org/1999/xhtml','http://www.w3.org/1999/xlink','http://www.w3.org/XML/1998/namespace','http://www.w3.org/2000/xmlns/']);
const classroomDirectory=ref=>typeof ref==='string'&&/^\/api\/classroom-media\/[A-Za-z0-9_-]+\/media\/$/.test(ref);
const staticPublic=ref=>typeof ref==='string'&&/^\/(?:review-assets\/v3-world-action\/[A-Za-z0-9_-]+\.(?:png|jpg|jpeg|webp)|avatars\/teacher-[1-9][0-9]*\.png)$/.test(ref);


function moduleSpecifiers(text){
 const source=ts.createSourceFile('module.js',text,ts.ScriptTarget.Latest,true,ts.ScriptKind.JS);
 const imports=[];
 if(source.parseDiagnostics.length)imports.push(null);
 const visit=node=>{
  if((ts.isImportDeclaration(node)||ts.isExportDeclaration(node))&&node.moduleSpecifier)imports.push(node.moduleSpecifier.text);
  if(ts.isCallExpression(node)&&node.expression.kind===ts.SyntaxKind.ImportKeyword){
   const value=node.arguments[0];imports.push(value&&(ts.isStringLiteral(value)||ts.isNoSubstitutionTemplateLiteral(value))?value.text:null);
  }
  ts.forEachChild(node,visit);
 };
 visit(source);return imports;
}
function mappedModule(specifier,imports,base){
 if(typeof specifier!=='string'||!specifier||/[\x00-\x20\x7f-\x9f]/.test(specifier))throw Error('module_specifier_invalid');
 let target=imports[specifier];
 if(target===undefined){
  const prefix=Object.keys(imports).filter(key=>key.endsWith('/')&&specifier.startsWith(key)).sort((a,b)=>b.length-a.length)[0];
  if(prefix){
   if(typeof imports[prefix]!=='string'||!imports[prefix].endsWith('/'))throw Error('module_prefix_invalid');
   target=new URL(specifier.slice(prefix.length),imports[prefix]).href;
  }
 }
 if(target!==undefined){if(typeof target!=='string')throw Error('module_target_invalid');return new URL(target).href;}
 if(/^https?:\/\//.test(specifier))return new URL(specifier).href;
 if(base&&/^\.{1,2}\//.test(specifier))return new URL(specifier,base).href;
 throw Error('module_specifier_unmapped');
}
function threeHtmlModules(document){
 const maps=[...document.querySelectorAll('script[type="importmap"]')],modules=[...document.querySelectorAll('script[type="module"]')];
 const active=maps.some(node=>/three/.test(node.textContent))||modules.some(node=>moduleSpecifiers(node.textContent).some(ref=>typeof ref==='string'&&/^(?:three(?:\/|$)|https:\/\/unpkg\.com\/three@)/.test(ref)));
 if(!active)return {scripts:new Set(),refs:[]};
 const refs=[],scripts=new Set(maps);let imports={};
 try{
  if(maps.length>1)throw Error('multiple_module_maps');
  for(const node of maps){
   const map=JSON.parse(node.textContent);
   if(!map||typeof map!=='object'||Array.isArray(map)||Object.keys(map).some(key=>key!=='imports')||!map.imports||typeof map.imports!=='object'||Array.isArray(map.imports)||Object.keys(map.imports).length>64)throw Error('module_map_invalid');
   imports=map.imports;
  }
 }catch{refs.push({ref:'mira:three-module-map-invalid',kind:'dependency'});}
 for(const script of modules){
  for(const specifier of moduleSpecifiers(script.textContent)){
   try{
    const ref=mappedModule(specifier,imports);refs.push({ref,kind:'dependency'});
    if(ref===THREE_BASE+'examples/jsm/controls/OrbitControls.js')refs.push({ref:mappedModule('three',imports),kind:'dependency'});
   }
   catch{refs.push({ref:specifier===null?'mira:three-computed-module-import':'mira:three-unmapped-module:'+encodeURIComponent(String(specifier)),kind:'dependency'});}
  }
 }
 return {scripts,refs};
}


// A bounded abstract value analysis, not a JavaScript interpreter. Only finite
// literal audio names may replace a directory literal; every unknown stays loud.
function finiteClassroomAudio(source){
 const prefix=/^\/api\/classroom-media\/[A-Za-z0-9_-]+\/audio\/$/;
 const prefixes=new Set(),nodes=[];
 const scan=node=>{nodes.push(node);if((ts.isStringLiteral(node)||ts.isNoSubstitutionTemplateLiteral(node)||ts.isTemplateHead(node))&&prefix.test(node.text))prefixes.add(node);ts.forEachChild(node,scan);};
 scan(source);
 const entries=[],provenLiterals=new Set();
 const unresolved=()=>({entries:[{ref:'mira:classroom-audio-analysis-unresolved',kind:'audio'}],provenLiterals:new Set()});
 if(source.parseDiagnostics.length&&(prefixes.size||/\/api\/classroom-media\/[A-Za-z0-9_-]+\/audio\/(?=['"`\s]|$)/.test(source.text)))return unresolved();
 if(!prefixes.size)return{entries,provenLiterals};
 const unsafePattern=nodes.some(node=>ts.isWithStatement(node)||ts.isForOfStatement(node)||ts.isForInStatement(node)
  ||((ts.isVariableDeclaration(node)||ts.isParameter(node))&&!ts.isIdentifier(node.name))
  ||(ts.isBinaryExpression(node)&&node.operatorToken.kind===ts.SyntaxKind.EqualsToken&&(ts.isArrayLiteralExpression(node.left)||ts.isObjectLiteralExpression(node.left)))
  ||(ts.isIdentifier(node)&&['eval','Function'].includes(node.text))
  ||(ts.isElementAccessExpression(node)&&['eval','Function'].includes(node.argumentExpression?.text)));
 if(unsafePattern)return unresolved();
 const limited=()=>({entries:[{ref:'mira:classroom-audio-analysis-limit',kind:'audio'}],provenLiterals:new Set()});
 if(nodes.length>20000)return limited();
 const scopes=new WeakMap(),decls=new WeakMap(),bindings=[],functions=[];let operations=0;
 const scope=(parent,fn=false)=>({parent,fn,bindings:new Map()});
 const outer=scope(null,true);
 const declare=(where,name,node)=>{
  if(!ts.isIdentifier(name))return;
  let binding=where.bindings.get(name.text);
  if(!binding){binding={name:name.text,defs:[],unsafe:false,escaped:false,value:null};where.bindings.set(name.text,binding);bindings.push(binding);}
  else binding.unsafe=true;
  decls.set(node,binding);return binding;
 };
 const bind=(node,current)=>{
  let here=current;
  if(ts.isFunctionLike(node)){
   let named;
   if(ts.isFunctionDeclaration(node)&&node.name)named=declare(current,node.name,node);
   here=scope(current,true);
   const fn={node,params:[],escaped:false,calls:0};functions.push(fn);
   if(named)named.fn=fn;
   for(const parameter of node.parameters||[]){const b=declare(here,parameter.name,parameter);if(b){if(parameter.initializer||parameter.dotDotDotToken)b.unsafe=true;fn.params.push(b);}else fn.escaped=true;}
  }else if(ts.isBlock(node)&&!ts.isFunctionLike(node.parent))here=scope(current);
  scopes.set(node,here);
  if(ts.isVariableDeclaration(node)){
   let owner=here;if(!(node.parent.flags&ts.NodeFlags.BlockScoped))while(owner.parent&&!owner.fn)owner=owner.parent;
   const b=declare(owner,node.name,node);if(b&&node.initializer)b.defs.push(node.initializer);
  }
  ts.forEachChild(node,child=>bind(child,here));
 };
 bind(source,outer);if(bindings.length>512)return limited();
 const lookup=node=>{if((ts.isPropertyAccessExpression(node.parent)||ts.isPropertyAssignment(node.parent))&&node.parent.name===node)return;let current=scopes.get(node);while(current){if(current.bindings.has(node.text))return current.bindings.get(node.text);current=current.parent;}};
 const escape=node=>{
  if(ts.isFunctionLike(node)||ts.isElementAccessExpression(node)||ts.isPropertyAccessExpression(node))return;
  if(ts.isIdentifier(node)){const b=lookup(node);if(b&&!b.fn)b.escaped=true;}
  ts.forEachChild(node,escape);
 };
 const candidates=[];
 for(const node of nodes){
  if(ts.isVariableDeclaration(node)&&node.initializer)candidates.push(node.initializer);
  if(ts.isReturnStatement(node)&&node.expression){candidates.push(node.expression);escape(node.expression);}
  if(ts.isBinaryExpression(node)&&node.operatorToken.kind>=ts.SyntaxKind.FirstAssignment&&node.operatorToken.kind<=ts.SyntaxKind.LastAssignment){
   candidates.push(node.right);
   if(ts.isIdentifier(node.left)){const b=lookup(node.left);if(b){if(node.operatorToken.kind===ts.SyntaxKind.EqualsToken)b.defs.push(node.right);else b.unsafe=true;}}
   else if((ts.isPropertyAccessExpression(node.left)||ts.isElementAccessExpression(node.left))&&ts.isIdentifier(node.left.expression)){
    const b=lookup(node.left.expression);if(b)b.unsafe=true;
    if(!ts.isPropertyAccessExpression(node.left)||!['src','href'].includes(node.left.name.text))escape(node.right);
   }
  }
  if((ts.isPrefixUnaryExpression(node)||ts.isPostfixUnaryExpression(node))&&[ts.SyntaxKind.PlusPlusToken,ts.SyntaxKind.MinusMinusToken].includes(node.operator)&&ts.isIdentifier(node.operand)){const b=lookup(node.operand);if(b)b.unsafe=true;}
  if(ts.isCallExpression(node)){
   const fn=ts.isIdentifier(node.expression)?lookup(node.expression)?.fn:undefined;
   if(fn){
    fn.calls++;
    for(const [i,b]of fn.params.entries()){if(!node.arguments[i]||node.arguments.some(ts.isSpreadElement))b.unsafe=true;else b.defs.push(node.arguments[i]);}
   }else{
    for(const argument of node.arguments)escape(argument);
    if((ts.isPropertyAccessExpression(node.expression)||ts.isElementAccessExpression(node.expression))&&ts.isIdentifier(node.expression.expression)){
     const method=ts.isPropertyAccessExpression(node.expression)?node.expression.name.text:node.expression.argumentExpression?.text;
     if(!['slice','shift','pop'].includes(method)){const b=lookup(node.expression.expression);if(b)b.unsafe=true;}
    }
   }
  }
  if(ts.isNewExpression(node))for(const argument of node.arguments||[])candidates.push(argument);
  if(ts.isIdentifier(node)){
   const fn=lookup(node)?.fn;
   if(fn&&!(ts.isFunctionDeclaration(node.parent)&&node.parent.name===node)&&!(ts.isCallExpression(node.parent)&&node.parent.expression===node))fn.escaped=true;
  }
 }
 for(const fn of functions)if(fn.escaped||!fn.calls)for(const b of fn.params)b.unsafe=true;

 const takeProof=new WeakMap();
 const guardedTake=node=>{
  if(takeProof.has(node))return takeProof.get(node);
  const prove=()=>{
   const receiver=node.expression.expression;if(!ts.isIdentifier(receiver))return false;
   const owner=lookup(receiver);if(!owner)return false;
   const group=new Set([owner]);let expanded=true;
   while(expanded){expanded=false;for(const [a,b]of aliases)if((group.has(a)||group.has(b))&&(!group.has(a)||!group.has(b))){group.add(a);group.add(b);expanded=true;}}
   const takes=nodes.filter(item=>ts.isCallExpression(item)&&ts.isPropertyAccessExpression(item.expression)&&['shift','pop'].includes(item.expression.name.text)&&ts.isIdentifier(item.expression.expression)&&group.has(lookup(item.expression.expression)));
   if(takes.length!==1)return false;
   let fn=node.parent;while(fn&&!ts.isFunctionLike(fn))fn=fn.parent;
   if(!fn||!fn.body||!ts.isBlock(fn.body))return false;
   const body=fn.body;let statement=node;
   while(statement.parent&&statement.parent!==body)statement=statement.parent;
   if(statement.parent!==body||(!ts.isVariableStatement(statement)&&!ts.isExpressionStatement(statement)))return false;
   const exits=then=>ts.isReturnStatement(then)||(ts.isBlock(then)&&then.statements.length&&ts.isReturnStatement(then.statements.at(-1)));
   for(const guard of body.statements){
    if(guard===statement)break;
    if(!ts.isIfStatement(guard)||guard.elseStatement||!exits(guard.thenStatement))continue;
    let condition=guard.expression;while(ts.isParenthesizedExpression(condition))condition=condition.expression;
    if(!ts.isPrefixUnaryExpression(condition)||condition.operator!==ts.SyntaxKind.ExclamationToken)continue;
    const length=condition.operand;
    if(!ts.isPropertyAccessExpression(length)||length.name.text!=='length'||!ts.isIdentifier(length.expression)||lookup(length.expression)!==owner)continue;
    const critical=nodes.filter(item=>item.pos>=guard.end&&item.end<=statement.end);
    const changes=critical.some(item=>{
     if(item===node)return false;
     if(ts.isCallExpression(item)||ts.isNewExpression(item)||ts.isAwaitExpression(item)||ts.isYieldExpression(item)||ts.isFunctionLike(item))return true;
     if(ts.isVariableDeclaration(item)&&group.has(decls.get(item)))return true;
     if(ts.isBinaryExpression(item)&&item.operatorToken.kind>=ts.SyntaxKind.FirstAssignment&&item.operatorToken.kind<=ts.SyntaxKind.LastAssignment){
      const left=item.left;
      if(ts.isIdentifier(left)&&group.has(lookup(left)))return true;
      if((ts.isPropertyAccessExpression(left)||ts.isElementAccessExpression(left))&&ts.isIdentifier(left.expression)&&group.has(lookup(left.expression)))return true;
     }
     return false;
    });
    if(!changes)return true;
   }
   return false;
  };
  const result=prove();takeProof.set(node,result);return result;
 };

 const value=(type='bottom',values=[],origins=[],lengths=[])=>({type,values:new Set(values),origins:new Set(origins),lengths:new Set(lengths)});
 const merge=(a,b)=>{
  if(!a)return b;if(!b)return a;
  const origins=new Set([...a.origins,...b.origins]);
  if(a.type==='bottom')return{...b,origins};if(b.type==='bottom')return{...a,origins};
  const type=a.type===b.type?a.type:'unknown',values=new Set([...a.values,...b.values]),lengths=new Set([...a.lengths,...b.lengths]);
  return values.size>128||type==='unknown'?value('unknown',[],origins):value(type,values,origins,lengths);
 };
 const unknown=(...items)=>value('unknown',[],items.flatMap(item=>[...(item?.origins||[])]));
 const join=(a,b,operator)=>{
  if(a.type==='bottom'||b.type==='bottom')return value('bottom',[],[...a.origins,...b.origins]);
  const strings=operator===ts.SyntaxKind.PlusToken&&[a.type,b.type].includes('string');
  if(!['string','number'].includes(a.type)||!['string','number'].includes(b.type)||(!strings&&(a.type!=='number'||b.type!=='number')))return unknown(a,b);
  const result=value(strings?'string':'number',[],[...a.origins,...b.origins]);
  for(const x of a.values)for(const y of b.values){
   const next=strings?String(x)+String(y):operator===ts.SyntaxKind.PlusToken?x+y:operator===ts.SyntaxKind.PercentToken&&y>0?x%y:NaN;
   if((typeof next==='number'&&!Number.isSafeInteger(next))||(typeof next==='string'&&next.length>4096))return unknown(a,b);
   result.values.add(next);if(result.values.size>128)return unknown(a,b);
  }
  return result;
 };
 let evaluationDepth=0;
 const evaluate=node=>{
  if(++evaluationDepth>64){evaluationDepth--;return value('unknown',[],prefixes);}
  try{return evaluateNode(node);}finally{evaluationDepth--;}
 };
 const evaluateNode=node=>{
  if(!node||++operations>200000)return value('unknown');
  if(ts.isParenthesizedExpression(node))return evaluate(node.expression);
  if(ts.isStringLiteral(node)||ts.isNoSubstitutionTemplateLiteral(node))return value('string',[node.text],prefixes.has(node)?[node]:[]);
  if(ts.isNumericLiteral(node))return value('number',[Number(node.text)]);
  if(ts.isIdentifier(node)){const b=lookup(node);return b?.value||value(b?'bottom':'unknown');}
  if(ts.isConditionalExpression(node))return merge(evaluate(node.whenTrue),evaluate(node.whenFalse));
  if(ts.isBinaryExpression(node)&&[ts.SyntaxKind.PlusToken,ts.SyntaxKind.PercentToken].includes(node.operatorToken.kind))return join(evaluate(node.left),evaluate(node.right),node.operatorToken.kind);
  if(ts.isTemplateExpression(node)){
   let result=value('string',[node.head.text],prefixes.has(node.head)?[node.head]:[]);
   for(const span of node.templateSpans)result=join(join(result,evaluate(span.expression),ts.SyntaxKind.PlusToken),value('string',[span.literal.text]),ts.SyntaxKind.PlusToken);
   return result;
  }
  if(ts.isArrayLiteralExpression(node)){
   let result=value('array',[],[],[node.elements.length]);
   for(const element of node.elements){const part=evaluate(element);if(!['string','number','bottom'].includes(part.type))return unknown(result,part);result=merge(result,value('array',part.values,part.origins,[node.elements.length]));}
   return result;
  }
  if(ts.isElementAccessExpression(node)){
   const array=evaluate(node.expression),index=evaluate(node.argumentExpression);
   if(array.type==='bottom'||index.type==='bottom')return value('bottom',[],[...array.origins,...index.origins]);
   if(array.type!=='array'||index.type!=='number'||!index.values.size||!array.lengths.size||[...index.values].some(i=>!Number.isSafeInteger(i)||i<0||[...array.lengths].some(n=>i>=n)))return unknown(array,index);
   const types=new Set([...array.values].map(item=>typeof item));return types.size===1?value([...types][0],array.values,[...array.origins,...index.origins]):unknown(array,index);
  }
  if(ts.isPropertyAccessExpression(node)){
   const owner=evaluate(node.expression);return node.name.text==='length'&&owner.type==='array'?value('number',owner.lengths,owner.origins):unknown(owner);
  }
  if(ts.isCallExpression(node)&&ts.isPropertyAccessExpression(node.expression)){
   const owner=evaluate(node.expression.expression),name=node.expression.name.text;
   if(owner.type==='bottom')return owner;
   if(owner.type==='array'&&!node.arguments.length&&name==='slice')return owner;
   if(owner.type==='array'&&!node.arguments.length&&['shift','pop'].includes(name)&&guardedTake(node)){
    const types=new Set([...owner.values].map(item=>typeof item));return !types.size?value('bottom',[],owner.origins):types.size===1?value([...types][0],owner.values,owner.origins):unknown(owner);
   }
   return unknown(owner,...node.arguments.map(evaluate));
  }
  if(ts.isCallExpression(node)||ts.isNewExpression(node))return unknown(...(node.arguments||[]).map(evaluate));
  return value('unknown',[],[...prefixes].filter(prefix=>prefix.pos>=node.pos&&prefix.end<=node.end));
 };
 const aliases=bindings.flatMap(b=>b.defs.filter(ts.isIdentifier).map(node=>[b,lookup(node)]).filter(([,other])=>other));
 const signature=item=>JSON.stringify([item.type,[...item.values].sort(),[...item.lengths].sort(),[...item.origins].map(node=>node.pos).sort()]);
 for(let pass=0;pass<32;pass++){
  let changed=false;
  for(const b of bindings){
   let next=b.defs.reduce((result,expr)=>merge(result,evaluate(expr)),value());
   if(next.type==='array')b.arrayLike=true;
   if(b.unsafe||(b.escaped&&(next.type==='array'||next.origins.size))||!b.defs.length)next=unknown(next);
   next=merge(b.value,next);
   if(!b.value||signature(next)!==signature(b.value)){b.value=next;changed=true;}
  }
  for(const [a,b]of aliases)if((a.arrayLike||b.arrayLike)&&(a.unsafe||b.unsafe||a.escaped||b.escaped)&&(!a.unsafe||!b.unsafe)){a.unsafe=b.unsafe=true;changed=true;}
  if(!changed)break;
  if(pass===31||operations>200000)return limited();
 }
 for(const expression of candidates){
  const result=evaluate(expression);if(operations>200000)return limited();if(!result.origins.size)continue;
  if(result.type==='string'&&[...result.values].every(ref=>prefix.test(ref)))continue;
  if(result.type==='string'&&result.values.size&&[...result.values].every(ref=>classroom(ref)&&/\/audio\/[^/]+\.wav$/.test(ref))){
   for(const ref of result.values)entries.push({ref,kind:'audio'});
   for(const node of result.origins)provenLiterals.add(node);
  }else entries.push({ref:'mira:classroom-audio-expression-unresolved:'+expression.pos,kind:'audio'});
 }
 return{entries,provenLiterals};
}

function htmlReferences(html){
 const result=[];
 if(typeof html!=='string'||!html)return result;
 const document=new DOMParser().parseFromString(html,'text/html');
 const threeModules=threeHtmlModules(document);result.push(...threeModules.refs);
 const add=(ref,kind)=>{if(typeof ref==='string'&&ref.trim())result.push({ref:ref.trim(),kind});};
 for(const node of document.querySelectorAll('img,video,audio,source,image,use,input[type="image"],object,embed,iframe,script[src],link[href]')){
  const tag=node.localName;
  const parent=node.parentElement?.localName;
  const kind=tag==='video'?'video':tag==='audio'?'audio':tag==='source'?(parent==='audio'?'audio':parent==='video'?'video':'image'):['img','image','input'].includes(tag)?'image':'dependency';
  add(node.getAttribute('src')||node.getAttribute('href')||node.getAttribute('xlink:href')||node.getAttribute('data'),kind);
  if(tag==='video')add(node.getAttribute('poster'),'poster');
  if(node.hasAttribute('srcset'))for(const entry of parseSrcset(node.getAttribute('srcset')))add(entry.url,kind);
  // Nested srcdoc is inert while parsing; its own media still belongs to the archive.
  if(tag==='iframe'&&node.hasAttribute('srcdoc'))result.push(...htmlReferences(node.getAttribute('srcdoc')));
 }
 for(const node of document.querySelectorAll('[style],style')){
  const css=node.localName==='style'?node.textContent:node.getAttribute('style');
  parseCssValue(css).walk(value=>{
   if(value.type==='function'&&value.value.toLowerCase()==='url'){
    add(parseCssValue.stringify(value.nodes).trim().replace(/^(['"])(.*)\1$/s,'$2'),'dependency');return false;
   }
  });
  // String-form @import does not have a url() node.
  for(const match of css.matchAll(/@import\s+(['"])([^'"\n]+)\1/gi))add(match[2],'dependency');
 }
 // Allocated ids interpolated by a generated activity's script have no DOM
 // src yet. Capture explicit literals; never run or evaluate the activity.
 for(const script of document.querySelectorAll('script')){
  if(threeModules.scripts.has(script))continue;
  // Parse JavaScript literals without evaluating it. A regexp over quoted
  // source accidentally retained the backslash in nested escaped SVG markup.
  const source=ts.createSourceFile('course.js',script.textContent,ts.ScriptTarget.Latest,true,ts.ScriptKind.JS);
  const inertJson=(script.getAttribute('type')||'').trim().toLowerCase().split(';')[0]==='application/json';
  const audio=inertJson?{entries:[],provenLiterals:new Set()}:finiteClassroomAudio(source);result.push(...audio.entries);
  const visit=node=>{
   if(ts.isStringLiteral(node)||ts.isNoSubstitutionTemplateLiteral(node)||ts.isTemplateHead(node)){
    const value=node.text;
    if(!audio.provenLiterals.has(node)&&!NAMESPACES.has(value)&&/^(?:ast_|https?:\/\/|\/\/|blob:|file:|\/api\/classroom-media\/|\/review-assets\/|\/avatars\/)/.test(value))add(value,'dependency');
    if(value.includes('<')&&value.includes('>'))result.push(...htmlReferences(value));
   }
   ts.forEachChild(node,visit);
  };
  visit(source);
 }
 return result;
}

export function enumerateSnapshotAssets(snapshot){
 if(!snapshot || !snapshot.stage || !Array.isArray(snapshot.scenes))throw Error('archive_asset_snapshot_invalid');
 const bridges=new Map();
 for(const scene of snapshot.scenes)for(const action of scene.actions || []){
  if(action.type==='speech' && plain(action.audioId) && (classroom(action.audioUrl)||inline(action.audioUrl))){
   const urls=bridges.get(action.audioId)||new Set();urls.add(action.audioUrl);bridges.set(action.audioId,urls);
  }
 }
 const allocated=[];
 const visit=value=>{
  if(Array.isArray(value)){for(const child of value)visit(child);return;}
  if(!value||typeof value!=='object')return;
  for(const [key,child]of Object.entries(value)){
   if(['allocatedAssetId','assetId'].includes(key)&&plain(child))allocated.push({ref:child,kind:'dependency'});
   else visit(child);
  }
 };
 visit(snapshot);
 const speechUrls=snapshot.scenes.flatMap(scene=>(scene.actions||[]).filter(action=>action.type==='speech'&&plain(action.audioUrl)).map(action=>({ref:action.audioUrl,kind:'audio'})));
 const discovered=[...enumerateAssetManifest(snapshot).entries,...snapshot.scenes.flatMap(scene=>htmlReferences(scene.content?.html)),...speechUrls,...allocated];
 const unique=new Map(discovered.map(entry=>[entry.kind+'\0'+entry.ref,entry]));
 return [...unique.values()].map(({ref,kind})=>{
  const urls=kind==='audio'?bridges.get(ref):undefined;
  const bridge=urls?.size===1?[...urls][0]:undefined;
  const effective=bridge || ref;
  return {ref,kind,...(bridge?{mappedRef:bridge}:{}),status:inline(effective)?'inline':classroom(effective)?'already_collected':'unresolved',
   ...(!inline(effective)&&!classroom(effective)?{reason:classroomDirectory(effective)?'controlled_classroom_media_directory':'asset_bytes_unresolved'}:{})};
 });
}

function dotenv(text){
 const values={};for(const line of text.split(/\r?\n/)){const m=line.match(/^\s*([A-Z_]+)\s*=\s*(.*?)\s*$/);if(m)values[m[1]]=m[2].replace(/^(['"])(.*)\1$/,'$2');}return values;
}
async function configuration(){
 let file={};try{file=dotenv(await fs.readFile(path.join(ROOT,'backend/.env'),'utf8'));}catch(error){if(error.code!=='ENOENT')throw error;}
 const value=key=>process.env[key] ?? file[key];
 // The launcher maps this backend-owned key to Native's DATABASE_URL. Never
 // infer the URL from a second dotenv or initialize application/schema writers.
 return {url:value('MIRA_OPENMAIC_AGENT_DATABASE_URL'),manifestPath:value('COURSE_STORAGE_MANIFEST_PATH'),bucket:value('ASSET_S3_BUCKET'),region:value('AWS_REGION')||value('AWS_DEFAULT_REGION'),
  endpoint:value('AWS_ENDPOINT_URL_S3')||value('AWS_ENDPOINT_URL'),accessKeyId:value('AWS_ACCESS_KEY_ID'),secretAccessKey:value('AWS_SECRET_ACCESS_KEY'),sessionToken:value('AWS_SESSION_TOKEN')};
}
async function directory(target,roots){
 if(typeof target!=='string'||!path.isAbsolute(target))throw Error('archive_asset_staging_invalid');
 const absolute=path.resolve(target);
 const allowed=roots.find(root=>absolute.startsWith(root+path.sep));
 if(!allowed)throw Error('archive_asset_staging_outside_private_root');
 // Walk all existing ancestors, including the trusted root itself; never
 // create or follow a symlink to a source or unrelated directory.
 let current=path.parse(absolute).root;
 for(const segment of absolute.slice(current.length).split(path.sep).filter(Boolean)){
  current=path.join(current,segment);
  try{const stat=await fs.lstat(current);if(stat.isSymbolicLink()||!stat.isDirectory())throw Error('archive_asset_staging_symlink');}
  catch(error){if(error.code!=='ENOENT')throw error;await fs.mkdir(current,{mode:0o700});}
 }
 return absolute;
}
async function readJson(filename){
 let current=filename;
 while(current!==path.dirname(current)){const stat=await fs.lstat(current);if(stat.isSymbolicLink())throw Error('archive_asset_authority_symlink');current=path.dirname(current);}
 const stat=await fs.stat(filename);if(!stat.isFile()||stat.size>MAX_INPUT)throw Error('archive_asset_authority_invalid');
 return JSON.parse(await fs.readFile(filename,'utf8'));
}
const references=snapshot=>new Set(enumerateSnapshotAssets(snapshot).map(e=>e.ref));

async function authorize(db,snapshot,stageId,dependencies){
 const own=await db.query('SELECT owner_id,data FROM document_stages WHERE id=$1',[stageId]);
 const stage=own.rows[0];
 const allowedShared=new Set();
 if(stage){
  const rows=await db.query('SELECT data FROM document_scenes WHERE stage_id=$1 ORDER BY scene_order,id',[stageId]);
  for(const ref of references({stage:stage.data,scenes:rows.rows.map(row=>row.data)}))allowedShared.add(ref);
 }
 const digest=sha(canonical(snapshot));
 const exists=await db.query("SELECT to_regclass('mira_course_archive_events') AS relation");
 let eventOwner;
 if(exists.rows[0]?.relation){
  const event=await db.query(`SELECT session.owner_id FROM mira_course_archive_events event
   LEFT JOIN agent_sessions session ON session.id=event.session_id
   WHERE event.stage_id=$1 AND event.source_digest=$2 AND event.snapshot_json=$3::jsonb LIMIT 1`,[stageId,digest,JSON.stringify(snapshot)]);
  if(event.rows.length){eventOwner=event.rows[0].owner_id;for(const ref of references(snapshot))allowedShared.add(ref);}
 }
 const nativeRoot=dependencies.nativeRoot||NATIVE;
 const paths=[path.join(nativeRoot,'data/classrooms',stageId+'.json'),path.join(nativeRoot,'data/classrooms',stageId,'artifact/classroom.json')];
 const state=dependencies.stateRoot||path.join(ROOT,'backend/data/course-storage');
 paths.push(path.join(state,'archive-events','legacy-'+sha(stageId+':'+digest)+'.json'));
 for(const filename of paths){
  try{
   const value=await readJson(filename),document=value.schemaVersion==='mira.course-archive.event.v1'?value.snapshot:value;
   if(document?.stage?.id!==stageId)continue;
   // Retained source documents may be a later revision: only the references
   // actually present in that authority qualify for shared-principal access.
   for(const ref of references(document))allowedShared.add(ref);
  }catch(error){if(error.code!=='ENOENT')throw error;}
 }
 return {owner:stage?.owner_id||eventOwner,allowedShared};
}
async function s3Bytes(config,hash,expected){
 const {S3Client,GetObjectCommand}=require('@aws-sdk/client-s3');
 const credentials=config.accessKeyId&&config.secretAccessKey?{accessKeyId:config.accessKeyId,secretAccessKey:config.secretAccessKey,...(config.sessionToken?{sessionToken:config.sessionToken}:{})}:undefined;
 const client=new S3Client({...(config.region?{region:config.region}:{}),...(config.endpoint?{endpoint:config.endpoint}:{}),...(credentials?{credentials}:{}),maxAttempts:2});
 try{
  const response=await client.send(new GetObjectCommand({Bucket:config.bucket,Key:hash}));
  const chunks=[];let size=0;
  for await(const chunk of response.Body){size+=chunk.length;if(size>expected){response.Body.destroy?.();throw Error('archive_asset_byte_size_mismatch');}chunks.push(chunk);}
  return Buffer.concat(chunks);
 }finally{client.destroy();}
}
function extension(mime,kind){
 const allowed={
  'image/png':'.png','image/jpeg':'.jpg','image/webp':'.webp','image/gif':'.gif','image/svg+xml':'.svg','image/avif':'.avif',
  'audio/wav':'.wav','audio/x-wav':'.wav','audio/mpeg':'.mp3','audio/ogg':'.ogg','audio/mp4':'.m4a','audio/webm':'.webm',
  'video/mp4':'.mp4','video/webm':'.webm','video/ogg':'.ogv',
  'application/pdf':'.pdf','model/gltf-binary':'.glb','font/woff':'.woff','font/woff2':'.woff2','font/ttf':'.ttf','font/otf':'.otf',
 };
 const family=kind==='audio'?'audio/':kind==='video'?'video/':'image/';
 return typeof mime==='string'&&(kind==='dependency'||mime.startsWith(family))?allowed[mime]:undefined;
}
export function assertAssetWriteBudget(stat,byteSize){
 const integer=value=>typeof value==='bigint'?value:Number.isSafeInteger(value)?BigInt(value):-1n;
 const blocks=integer(stat.bavail),blockSize=integer(stat.bsize);
 if(blocks<0n||blockSize<=0n||!Number.isSafeInteger(byteSize)||byteSize<0)throw Error('archive_asset_disk_space_unavailable');
 if(blocks*blockSize<BigInt(byteSize)+1024n**3n)throw Error('archive_asset_disk_space_insufficient');
}
export async function saveBytes(root,digest,ext,bytes,{statfs=fs.statfs}={}){
 const filename=path.join(root,digest+ext);
 const existing=async()=>{
  const stat=await fs.lstat(filename);
  if(stat.isSymbolicLink()||!stat.isFile()||stat.size!==bytes.length||sha(await fs.readFile(filename))!==digest)throw Error('archive_asset_staging_conflict');
  return filename;
 };
 try{return await existing();}catch(error){if(error.code!=='ENOENT')throw error;}
 // Reserve space only for a genuinely new copy. Verified cache hits remain
 // readable when free disk has fallen below the one-GiB write reserve.
 assertAssetWriteBudget(await statfs(root),bytes.length);
 try{const handle=await fs.open(filename,'wx',0o600);try{await handle.writeFile(bytes);await handle.sync();}finally{await handle.close();}}
 catch(error){if(error.code!=='EEXIST')throw error;await existing();}
 return filename;
}
async function publicBytes(ref,nativeRoot){
 const root=path.join(nativeRoot,'public'),filename=path.resolve(root,'.'+ref);
 if(!filename.startsWith(root+path.sep)||await fs.realpath(filename)!==filename)throw Error('archive_static_source_path_invalid');
 let current=filename;
 while(current!==path.dirname(root)){const stat=await fs.lstat(current);if(stat.isSymbolicLink())throw Error('archive_static_source_symlink');current=path.dirname(current);}
 const stat=await fs.stat(filename);if(!stat.isFile()||stat.size<1||stat.size>32*1024**2)throw Error('archive_static_source_invalid');
 return fs.readFile(filename);
}
async function directoryChildren(ref,config,dependencies){
 const parts=ref.split('/'),stageId=parts[3],nativeRoot=dependencies.nativeRoot||NATIVE;
 const sourcePrefix='openmaic-runtime/.runtime/OpenMAIC/data/classrooms/'+stageId+'/media/';
 const filenames=new Set(),safeImage=name=>/^[A-Za-z0-9_.-]+\.(?:png|jpg|jpeg|webp|gif|avif|svg)$/i.test(name)&&!name.includes('..');
 const directory=path.join(nativeRoot,'data/classrooms',stageId,'media');
 try{
  if(await fs.realpath(directory)!==directory)throw Error('archive_media_directory_symlink');
  let current=directory;while(current!==path.dirname(nativeRoot)){if((await fs.lstat(current)).isSymbolicLink())throw Error('archive_media_directory_symlink');current=path.dirname(current);}
  const names=await fs.readdir(directory,{withFileTypes:true});
  if(names.length>512)throw Error('archive_media_directory_limit');
  for(const entry of names){if(entry.isSymbolicLink())throw Error('archive_media_directory_symlink');if(entry.isFile()&&safeImage(entry.name))filenames.add(entry.name);}
 }catch(error){if(error.code!=='ENOENT')throw error;}
 if(config.manifestPath){
  const manifest=await readJson(config.manifestPath);
  if(!['mira.course-storage.manifest.v1','mira.course-storage.manifest.v2'].includes(manifest.schemaVersion)||!Array.isArray(manifest.files))throw Error('archive_media_manifest_invalid');
  for(const file of manifest.files){
   if(typeof file.path!=='string'||!file.path.startsWith(sourcePrefix))continue;
   const name=file.path.slice(sourcePrefix.length);
   if(safeImage(name)&&/^image\//.test(file.mimeType||'')&&/^[a-f0-9]{64}$/.test(file.sha256||'')&&Number.isSafeInteger(file.byteSize)&&file.byteSize>0)filenames.add(name);
  }
 }
 if(filenames.size===0||filenames.size>512)throw Error('archive_media_directory_unavailable_or_oversized');
 return [...filenames].sort().map(name=>({ref:ref+name,kind:'image',status:'already_collected'}));
}

function katexName(ref,fonts=false){
 if(typeof ref!=='string'||!ref.startsWith(KATEX_BASE))return;
 const name=ref.slice(KATEX_BASE.length);
 if(Object.hasOwn(KATEX_FILES,name)&&(KATEX_ENTRIES.has(name)||(fonts&&name.startsWith('fonts/'))))return name;
}
export function publicCdnAddress(address){
 if(isIP(address)===4){
  const [a,b,c]=address.split('.').map(Number);
  return a>0&&a<224&&a!==10&&a!==127&&!(a===100&&b>=64&&b<=127)&&!(a===169&&b===254)
   &&!(a===172&&b>=16&&b<=31)&&!(a===192&&(b===0||b===168||b===88))
   &&!(a===198&&(b===18||b===19||(b===51&&c===100)))&&!(a===203&&b===0&&c===113);
 }
 return isIP(address)===6&&/^[23][0-9a-f]{3}:/i.test(address)
  &&!/^2001:(?:db8:|0:|:|10:|20:)/i.test(address)&&!/^2002:|^3fff:/i.test(address);
}
function publicCdnLookup(hostname,options,callback){
 if(hostname!=='cdn.jsdelivr.net'){callback(Error('archive_cdn_host_rejected'));return;}
 dnsLookup(hostname,{all:true,verbatim:true},(error,addresses)=>{
  if(error){callback(error);return;}
  if(!addresses.length||addresses.some(item=>!publicCdnAddress(item.address))){callback(Error('archive_cdn_private_address'));return;}
  const selected=addresses.filter(item=>!options.family||item.family===options.family);
  if(!selected.length){callback(Error('archive_cdn_address_unavailable'));return;}
  if(options.all)callback(null,selected);else callback(null,selected[0].address,selected[0].family);
 });
}
export function downloadKatexBytes(url,{maxBytes,timeoutMs=10000,request=https.get}={}){
 if(!katexName(url,true)||!Number.isSafeInteger(maxBytes)||maxBytes<1||maxBytes>512*1024)throw Error('archive_cdn_request_rejected');
 return new Promise((resolve,reject)=>{
  let req,timer,settled=false;
  const finish=(error,bytes)=>{if(settled)return;settled=true;clearTimeout(timer);error?reject(error):resolve(bytes);};
  req=request(url,{agent:false,lookup:publicCdnLookup,maxHeaderSize:16384,
   headers:{'Accept-Encoding':'identity','User-Agent':'Mira-course-archive/1'}},response=>{
   response.on('error',error=>finish(error));
   const fail=()=>{response.destroy();req?.destroy();finish(Error('archive_cdn_response_rejected'));};
   // Redirect budget is zero: never follow a Location to another origin or IP.
   if(response.statusCode!==200||(response.headers['content-encoding']&&response.headers['content-encoding']!=='identity')){fail();return;}
   const length=response.headers['content-length'];
   if(length!==undefined&&(!/^\d+$/.test(length)||Number(length)!==maxBytes)){fail();return;}
   const chunks=[];let size=0;
   response.on('data',chunk=>{size+=chunk.length;if(size>maxBytes){fail();return;}chunks.push(chunk);});
   response.on('end',()=>size===maxBytes?finish(null,Buffer.concat(chunks)):finish(Error('archive_cdn_size_mismatch')));
  });
  req.on('error',error=>finish(error));
  timer=setTimeout(()=>{req.destroy();finish(Error('archive_cdn_timeout'));},Math.max(1,Math.min(timeoutMs,10000)));
 });
}
async function pinnedFile(root,name,pin){
 const filename=path.join(root,name);
 if(await fs.realpath(filename)!==filename)throw Error('archive_cdn_source_linked');
 const handle=await fs.open(filename,fsConstants.O_RDONLY|fsConstants.O_NOFOLLOW);
 try{
  const before=await handle.stat();if(!before.isFile()||before.size!==pin[0])throw Error('archive_cdn_source_size');
  const buffer=Buffer.alloc(pin[0]+1);let size=0;
  while(size<buffer.length){const {bytesRead}=await handle.read(buffer,size,buffer.length-size,null);if(!bytesRead)break;size+=bytesRead;}
  const bytes=buffer.subarray(0,size),after=await handle.stat(),current=await fs.lstat(filename);
  if(bytes.length!==pin[0]||sha(bytes)!==pin[1]||['dev','ino','size','mtimeMs','ctimeMs'].some(k=>before[k]!==after[k]||before[k]!==current[k]))throw Error('archive_cdn_source_changed');
  return bytes;
 }finally{await handle.close();}
}
/** The optional pin/transport seams are for offline tests, never document input. */
export function createKatexArchiveResolver({root,cacheRoot=root,localRoot,pins=KATEX_FILES,fetchBytes=downloadKatexBytes,limits={}}){
 const maxRequests=Math.min(limits.requests??64,64),maxTotal=Math.min(limits.totalBytes??2*1024**2,2*1024**2);
 const deadline=Date.now()+Math.min(limits.timeoutMs??60000,60000);
 const records=new Map();let requests=0,total=0;
 const local=async(name,pin)=>{
  if(!localRoot)return;
  try{
   const directory=await fs.realpath(localRoot),info=await readJson(path.join(directory,'package.json'));
   if(info.name!=='katex'||info.version!=='0.16.9')return;
   return await pinnedFile(path.join(directory,'dist'),name,pin);
  }catch{return;}
 };
 const load=name=>{
  if(records.has(name))return records.get(name);
  const promise=(async()=>{
   const ref=KATEX_BASE+name,entry={ref,originalURL:ref,kind:'dependency',status:'unresolved',reason:'versioned_public_dependency_unavailable'};
   try{
    const pin=pins[name];
    if(!Object.hasOwn(KATEX_FILES,name)||!Array.isArray(pin)||!Number.isSafeInteger(pin[0])||pin[0]<1||pin[0]>512*1024||!/^[a-f0-9]{64}$/.test(pin[1]))throw Error('archive_cdn_pin_invalid');
    if(Date.now()>deadline)throw Error('archive_cdn_deadline');
    const ext=path.extname(name),cached=pin[1]+ext;
    let bytes;
    try{bytes=await pinnedFile(cacheRoot,cached,pin);}catch(error){if(error.code!=='ENOENT')throw error;}
    if(!bytes)bytes=await local(name,pin);
    if(!bytes){
     if(++requests>maxRequests||(total+=pin[0])>maxTotal)throw Error('archive_cdn_budget');
     bytes=await fetchBytes(ref,{maxBytes:pin[0],timeoutMs:Math.max(1,Math.min(10000,deadline-Date.now()))});
    }
    if(!(bytes instanceof Uint8Array)||bytes.length!==pin[0]||sha(bytes)!==pin[1])throw Error('archive_cdn_integrity');
    bytes=Buffer.from(bytes);
    await saveBytes(cacheRoot,pin[1],ext,bytes);
    const mimeType={'.css':'text/css','.js':'application/javascript','.woff2':'font/woff2','.woff':'font/woff','.ttf':'font/ttf'}[ext];
    Object.assign(entry,{status:'resolved',sourcePath:await saveBytes(root,pin[1],ext,bytes),sha256:pin[1],byteSize:bytes.length,mimeType,
     packageName:'katex',packageVersion:'0.16.9'});delete entry.reason;
    return {entry,bytes};
   }catch{return {entry};}
  })();records.set(name,promise);return promise;
 };
 return async ref=>{
  const name=katexName(ref);if(!name)throw Error('archive_cdn_url_rejected');
  const {entry,bytes}=await load(name);
  if(name!=='katex.min.css'||entry.status!=='resolved')return [entry];
  const children=[];
  try{
   const css=bytes.toString('utf8');if(/@import\b/i.test(css))throw Error('archive_cdn_css_import_rejected');
   parseCssValue(css).walk(value=>{
    if(value.type!=='function'||value.value.toLowerCase()!=='url')return;
    const relative=parseCssValue.stringify(value.nodes).trim().replace(/^(['"])(.*)\1$/s,'$2');
    const url=new URL(relative,ref).href,child=katexName(url,true);
    if(!child?.startsWith('fonts/'))throw Error('archive_cdn_css_reference_rejected');
    if(!children.some(item=>item.ref===url))children.push({ref:url,name:child,relativeRef:relative});return false;
   });
   if(!children.length||children.length>60)throw Error('archive_cdn_font_limit');
   const dependencies=[];
   for(let i=0;i<children.length;i+=4){
    const chunk=await Promise.all(children.slice(i,i+4).map(async child=>({...(await load(child.name)).entry,
     relativeRef:child.relativeRef,dependencyOf:ref})));
    dependencies.push(...chunk);
   }
   if(dependencies.some(child=>child.status!=='resolved')){entry.status='unresolved';entry.reason='versioned_public_dependency_incomplete';}
   entry.dependencyRefs=children.map(child=>child.ref);
   return [entry,...dependencies];
  }catch{entry.status='unresolved';entry.reason='versioned_public_dependency_incomplete';return [entry];}
 };
}


function threeName(ref,evidence=false){
 if(typeof ref!=='string'||!ref.startsWith(THREE_BASE))return;
 const name=ref.slice(THREE_BASE.length);
 if(Object.hasOwn(THREE_FILES,name)&&(evidence||THREE_ENTRIES.has(name)))return name;
}
function threeCdnLookup(hostname,options,callback){
 if(hostname!=='unpkg.com'){callback(Error('archive_three_host_rejected'));return;}
 dnsLookup(hostname,{all:true,verbatim:true},(error,addresses)=>{
  if(error){callback(error);return;}
  if(!addresses.length||addresses.some(item=>!publicCdnAddress(item.address))){callback(Error('archive_cdn_private_address'));return;}
  const selected=addresses.filter(item=>!options.family||item.family===options.family);
  if(!selected.length){callback(Error('archive_cdn_address_unavailable'));return;}
  if(options.all)callback(null,selected);else callback(null,selected[0].address,selected[0].family);
 });
}
export function downloadThreeBytes(url,{maxBytes,timeoutMs=10000,request=https.get}={}){
 if(!threeName(url,true)||!Number.isSafeInteger(maxBytes)||maxBytes<1||maxBytes>2*1024**2)throw Error('archive_three_request_rejected');
 return new Promise((resolve,reject)=>{
  let req,timer,settled=false;
  const finish=(error,bytes)=>{if(settled)return;settled=true;clearTimeout(timer);error?reject(error):resolve(bytes);};
  req=request(url,{agent:false,lookup:threeCdnLookup,maxHeaderSize:16384,
   headers:{'Accept-Encoding':'identity','User-Agent':'Mira-course-archive/1'}},response=>{
   response.on('error',error=>finish(error));
   const fail=()=>{response.destroy();req?.destroy();finish(Error('archive_cdn_response_rejected'));};
   if(response.statusCode!==200||(response.headers['content-encoding']&&response.headers['content-encoding']!=='identity')){fail();return;}
   const length=response.headers['content-length'];
   if(length!==undefined&&(!/^\d+$/.test(length)||Number(length)!==maxBytes)){fail();return;}
   const chunks=[];let size=0;
   response.on('data',chunk=>{size+=chunk.length;if(size>maxBytes){fail();return;}chunks.push(chunk);});
   response.on('end',()=>size===maxBytes?finish(null,Buffer.concat(chunks)):finish(Error('archive_cdn_size_mismatch')));
  });
  req.on('error',error=>finish(error));
  timer=setTimeout(()=>{req.destroy();finish(Error('archive_cdn_timeout'));},Math.max(1,Math.min(timeoutMs,10000)));
 });
}
/** Test-only pins/transports are dependency injection, never document fields. */
export function createThreeArchiveResolver({root,cacheRoot=root,localRoot,pins=THREE_FILES,fetchBytes=downloadThreeBytes,limits={}}){
 const maxRequests=Math.min(limits.requests??4,4),maxTotal=Math.min(limits.totalBytes??4*1024**2,4*1024**2);
 const deadline=Date.now()+Math.min(limits.timeoutMs??60000,60000),records=new Map();let requests=0,total=0;
 const load=name=>{
  if(records.has(name))return records.get(name);
  const promise=(async()=>{
   const ref=THREE_BASE+name,entry={ref,originalURL:ref,kind:'dependency',status:'unresolved',reason:'versioned_public_dependency_unavailable'};
   try{
    const pin=pins[name];
    if(!Object.hasOwn(THREE_FILES,name)||!Array.isArray(pin)||!Number.isSafeInteger(pin[0])||pin[0]<1||pin[0]>2*1024**2||!/^[a-f0-9]{64}$/.test(pin[1]))throw Error('archive_three_pin_invalid');
    if(Date.now()>deadline||(total+=pin[0])>maxTotal)throw Error('archive_three_budget');
    const ext=path.extname(name),cached=pin[1]+ext;let bytes;
    try{bytes=await pinnedFile(cacheRoot,cached,pin);}catch(error){if(error.code!=='ENOENT')throw error;}
    if(!bytes&&localRoot){
     try{
      const directory=await fs.realpath(localRoot),info=await readJson(path.join(directory,'package.json'));
      if(info.name==='three'&&info.version==='0.160.0')bytes=await pinnedFile(directory,name,pin);
     }catch{}
    }
    if(!bytes){
     if(++requests>maxRequests)throw Error('archive_three_request_budget');
     bytes=await fetchBytes(ref,{maxBytes:pin[0],timeoutMs:Math.max(1,Math.min(10000,deadline-Date.now()))});
    }
    if(!(bytes instanceof Uint8Array)||bytes.length!==pin[0]||sha(bytes)!==pin[1])throw Error('archive_three_integrity');
    bytes=Buffer.from(bytes);await saveBytes(cacheRoot,pin[1],ext,bytes);
    const mimeType=name.endsWith('.js')?'application/javascript':name==='package.json'?'application/json':'text/plain';
    Object.assign(entry,{status:'resolved',sourcePath:await saveBytes(root,pin[1],ext,bytes),sha256:pin[1],byteSize:bytes.length,mimeType,
     packageName:'three',packageVersion:'0.160.0'});delete entry.reason;
    return {entry,bytes};
   }catch{return {entry};}
  })();records.set(name,promise);return promise;
 };
 return async ref=>{
  const name=threeName(ref);if(!name)throw Error('archive_three_url_rejected');
  const results=[],visited=new Set();
  const visit=async current=>{
   if(visited.has(current))return;visited.add(current);
   const value=await load(current);results.push(value.entry);
   if(value.entry.status!=='resolved'||!current.endsWith('.js'))return;
   const dependencies=[];
   for(const specifier of moduleSpecifiers(value.bytes.toString('utf8'))){
    const url=mappedModule(specifier,{three:THREE_BASE+'build/three.module.js','three/addons/':THREE_BASE+'examples/jsm/'},THREE_BASE+current),child=threeName(url);
    if(!child)throw Error('archive_three_dependency_unpinned');
    dependencies.push(url);await visit(child);
   }
   value.entry.dependencyRefs=[...new Set(dependencies)];
  };
  try{
   await visit(name);
   for(const evidence of ['LICENSE','package.json']){
    const item=(await load(evidence)).entry;results.push({...item,dependencyOf:ref,packageEvidence:true});
   }
   if(results.some(item=>item.status!=='resolved'))throw Error('archive_three_dependency_incomplete');
   results[0].packageEvidenceRefs=['LICENSE','package.json'].map(name=>THREE_BASE+name);
  }catch{
   if(!results.length)results.push((await load(name)).entry);
   results[0]={...results[0],status:'unresolved',reason:'versioned_public_dependency_incomplete'};
  }
  return results;
 };
}

export async function resolveArchiveAssets(input,dependencies={}){
 const {snapshot,stageId,stagingRoot}=input;
 if(typeof stageId!=='string'||!/^[A-Za-z0-9_-]{1,255}$/.test(stageId)||snapshot?.stage?.id!==stageId)throw Error('archive_asset_stage_identity_invalid');
 const entries=enumerateSnapshotAssets(snapshot);
 if(entries.length>12000)throw Error('archive_asset_reference_limit');
 if(!entries.some(e=>e.status==='unresolved'))return {schemaVersion:'mira.course-archive.assets.v1',entries,unresolved:[]};
 const roots=dependencies.allowedRoots||[path.join(ROOT,'backend/data/course-storage/archives'),...(process.env.MIRA_TASK_TMPDIR?[await fs.realpath(process.env.MIRA_TASK_TMPDIR)]:[])];
 const target=await directory(stagingRoot,roots);
 const config=dependencies.config||await configuration();
 let katex,three;
 for(const entry of [...entries]){
  if(entry.status!=='unresolved')continue;
  if(threeName(entry.ref)){
   try{
    if(!three){
     const state=dependencies.stateRoot||path.join(ROOT,'backend/data/course-storage');
     const cache=await directory(path.join(state,'public-dependency-cache/three-0.160.0'),dependencies.allowedRoots||[state,...roots]);
     let localRoot;try{localRoot=path.dirname(require.resolve('three/package.json'));}catch{}
     three=createThreeArchiveResolver({root:target,cacheRoot:cache,localRoot,fetchBytes:dependencies.downloadThreeBytes||downloadThreeBytes});
    }
    const [resolved,...children]=await three(entry.ref);Object.assign(entry,resolved);
    if(entry.status==='resolved')delete entry.reason;
    for(const child of children)if(!entries.some(existing=>existing.ref===child.ref))entries.push(child);
   }catch{entry.reason='versioned_public_dependency_unavailable';}
  }else if(katexName(entry.ref)){
   try{
    if(!katex){
     const state=dependencies.stateRoot||path.join(ROOT,'backend/data/course-storage');
     const cache=await directory(path.join(state,'public-dependency-cache/katex-0.16.9'),dependencies.allowedRoots||[state,...roots]);
     let localRoot;try{localRoot=path.dirname(require.resolve('katex/package.json'));}catch{}
     katex=createKatexArchiveResolver({root:target,cacheRoot:cache,localRoot,fetchBytes:dependencies.downloadKatexBytes||downloadKatexBytes});
    }
    const [resolved,...children]=await katex(entry.ref);Object.assign(entry,resolved);
    if(entry.status==='resolved')delete entry.reason;
    for(const child of children)if(!entries.some(existing=>existing.ref===child.ref))entries.push(child);
   }catch{entry.reason='versioned_public_dependency_unavailable';}
  }else if(staticPublic(entry.ref)){
   try{
    const bytes=await publicBytes(entry.ref,dependencies.nativeRoot||NATIVE),digest=sha(bytes),ext=path.extname(entry.ref).toLowerCase();
    const mimeType={'.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp'}[ext];
    Object.assign(entry,{status:'resolved',sourcePath:await saveBytes(target,digest,ext,bytes),sha256:digest,byteSize:bytes.length,mimeType});delete entry.reason;
   }catch{entry.reason='controlled_public_asset_missing_or_invalid';}
  }else if(classroomDirectory(entry.ref)){
   try{entries.push(...await directoryChildren(entry.ref,config,dependencies));entry.status='already_collected';entry.expandedDirectory=true;delete entry.reason;}
   catch{entry.reason='controlled_classroom_media_directory_unavailable';}
  }
 }
 const pending=entries.filter(e=>e.status==='unresolved'&&!staticPublic(e.ref)&&!classroomDirectory(e.ref)&&plain(e.ref)&&!/^(?:[a-z][a-z0-9+.-]*:|\/)/i.test(e.ref));
 if(!pending.length)return {schemaVersion:'mira.course-archive.assets.v1',entries,unresolved:entries.filter(e=>e.status==='unresolved')};
 let db=dependencies.db;
 if(!db){
  if(!config.url||!['postgres:','postgresql:'].includes(new URL(config.url).protocol))throw Error('archive_asset_database_unavailable');
  const {Client}=require('pg');db=new Client({connectionString:config.url,statement_timeout:30000,connectionTimeoutMillis:10000});await db.connect();
 }
 try{
  await db.query('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY');
  const authority=await authorize(db,snapshot,stageId,dependencies);
  const cache=new Map();let total=0;
  for(const entry of pending){
   const {ref,kind}=entry;
   // Never fetch a URL taken from document content. Only the registry's exact
   // opaque ID is queried, then its content hash selects an existing byte layer.
   if(!plain(ref)||/^(?:[a-z][a-z0-9+.-]*:|\/)/i.test(ref)){entry.reason='unsupported_external_asset_reference';continue;}
   try{
    let result=cache.get(ref);
    if(!result){
     const rows=await db.query(`SELECT entry.content_hash,entry.mime,blob.byte_size
      FROM asset_entries entry JOIN asset_blobs blob ON blob.content_hash=entry.content_hash
      WHERE entry.id=$1 AND (entry.principal=$2 OR ($3::boolean AND entry.principal='shared'))
      ORDER BY CASE WHEN entry.principal=$2 THEN 0 ELSE 1 END LIMIT 1`,[ref,authority.owner||null,authority.allowedShared.has(ref)]);
     const row=rows.rows[0],size=Number(row?.byte_size);
     if(!row||!/^sha256-[a-f0-9]{64}$/.test(row.content_hash)||!Number.isSafeInteger(size)||size<1||size>MAX_BYTES)throw Error('archive_asset_identity_missing_or_oversized');
     let bytes;
     if(dependencies.readBytes)bytes=await dependencies.readBytes(row.content_hash,size);
     else if(config.bucket)bytes=await s3Bytes(config,row.content_hash,size);
     else{const value=await db.query('SELECT bytes FROM asset_blobs WHERE content_hash=$1',[row.content_hash]);bytes=value.rows[0]?.bytes;}
     if(!bytes||bytes.length!==size||sha(bytes)!==row.content_hash.slice(7))throw Error('archive_asset_bytes_invalid');
     total+=size;if(total>MAX_TOTAL)throw Error('archive_asset_total_limit');
     const ext=extension(row.mime,kind);if(!ext)throw Error('archive_asset_mime_kind_mismatch');
     const digest=sha(bytes),sourcePath=await saveBytes(target,digest,ext,bytes);
     result={sourcePath,sha256:digest,byteSize:size,mimeType:row.mime};cache.set(ref,result);
    }
    const ext=extension(result.mimeType,kind);if(!ext)throw Error('archive_asset_mime_kind_mismatch');
    Object.assign(entry,{status:'resolved',...result});delete entry.reason;
   }catch{entry.reason='asset_bytes_unavailable_or_invalid';}
  }
  await db.query('ROLLBACK');
  return {schemaVersion:'mira.course-archive.assets.v1',entries,unresolved:entries.filter(e=>e.status==='unresolved')};
 }catch(error){await db.query('ROLLBACK').catch(()=>{});throw error;}
 finally{if(!dependencies.db)await db.end();}
}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 let raw='';try{
  for await(const chunk of process.stdin){raw+=chunk;if(Buffer.byteLength(raw)>MAX_INPUT)throw Error('archive_asset_input_limit');}
  console.log(JSON.stringify(await resolveArchiveAssets(JSON.parse(raw))));
 }catch{console.error(JSON.stringify({error:'course_archive_assets_failed'}));process.exitCode=1;}
}
