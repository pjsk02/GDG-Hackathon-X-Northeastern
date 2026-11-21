/* esm.sh - @a2ui/web_core@0.15.0/v0_8 */
var de=Object.defineProperty;var ce=(t,e)=>{for(var r in e)de(t,r,{get:e[r],enumerable:!0})};var P={};ce(P,{A2UIValidationEvent:()=>$});var $=class t extends CustomEvent{constructor(e,r){super(t.EVENT_NAME,{bubbles:!0,composed:!0,...r,detail:{...e,eventType:t.EVENT_NAME}})}};$.EVENT_NAME="a2ui-validation-input";function $e(t){return l(t)&&"key"in t}function M(t,e){return t==="path"&&typeof e=="string"}function l(t){return typeof t=="object"&&t!==null&&!Array.isArray(t)}function U(t){return l(t)?"explicitList"in t||"template"in t:!1}function b(t){return l(t)&&("path"in t||"literal"in t&&typeof t.literal=="string"||"literalString"in t)}function he(t){return l(t)&&("path"in t||"literal"in t&&typeof t.literal=="number"||"literalNumber"in t)}function fe(t){return l(t)&&("path"in t||"literal"in t&&typeof t.literal=="boolean"||"literalBoolean"in t)}function g(t){return!(!l(t)||!("id"in t&&"type"in t&&"properties"in t))}function D(t){return l(t)&&"url"in t&&b(t.url)}function k(t){return l(t)&&"child"in t&&g(t.child)&&"action"in t}function z(t){return l(t)?"child"in t?g(t.child):"children"in t?Array.isArray(t.children)&&t.children.every(g):!1:!1}function O(t){return l(t)&&"label"in t&&b(t.label)&&"value"in t&&fe(t.value)}function q(t){return l(t)&&"children"in t&&Array.isArray(t.children)&&t.children.every(g)}function N(t){return l(t)&&"value"in t&&b(t.value)}function B(t){return l(t)}function F(t){return l(t)&&"url"in t&&b(t.url)}function E(t){return l(t)&&"name"in t&&b(t.name)}function V(t){return l(t)&&"children"in t&&Array.isArray(t.children)&&t.children.every(g)}function L(t){return l(t)&&"entryPointChild"in t&&g(t.entryPointChild)&&"contentChild"in t&&g(t.contentChild)}function _(t){return l(t)&&"selections"in t}function K(t){return l(t)&&"children"in t&&Array.isArray(t.children)&&t.children.every(g)}function W(t){return l(t)&&"value"in t&&he(t.value)}function ue(t){return l(t)&&"title"in t&&b(t.title)&&"child"in t&&g(t.child)}function H(t){return l(t)&&"tabItems"in t&&Array.isArray(t.tabItems)&&t.tabItems.every(ue)}function G(t){return l(t)&&"text"in t&&b(t.text)}function J(t){return l(t)&&"label"in t&&b(t.label)}function Y(t){return l(t)&&"url"in t&&b(t.url)}import{A2uiMessageSchema as ye}from"/vendor/esm/@a2ui/web_core@0.15.0/X-ZGxpdEAzLjMuMw/es2022/src/v0_8/schema/server-to-client.mjs";var x=class extends Error{constructor(e,r="UNKNOWN_ERROR"){super(e),this.name=this.constructor.name,this.code=r,Error.captureStackTrace&&Error.captureStackTrace(this,this.constructor)}},u=class extends x{constructor(e,r){super(e,"VALIDATION_ERROR"),this.details=r}},X=class extends x{constructor(e,r){super(e,"DATA_ERROR"),this.path=r}},Q=class extends x{constructor(e,r){super(e,"EXPRESSION_ERROR"),this.expression=r}},I=class extends x{constructor(e){super(e,"STATE_ERROR")}};var A=class t{constructor(e={mapCtor:Map,arrayCtor:Array,setCtor:Set,objCtor:Object}){this.opts=e,this.mapCtor=Map,this.arrayCtor=Array,this.setCtor=Set,this.objCtor=Object,this.arrayCtor=e.arrayCtor,this.mapCtor=e.mapCtor,this.setCtor=e.setCtor,this.objCtor=e.objCtor,this.surfaces=new e.mapCtor}getSurfaces(){let e=this.surfaces,r=new Map;for(let[i,o]of e)o.rootComponentId&&r.set(i,o);return r}clearSurfaces(){this.surfaces.clear()}processMessages(e){for(let r of e){let i=ye.parse(r);i.beginRendering&&this.handleBeginRendering(i.beginRendering,i.beginRendering.surfaceId),i.surfaceUpdate&&this.handleSurfaceUpdate(i.surfaceUpdate,i.surfaceUpdate.surfaceId),i.dataModelUpdate&&this.handleDataModelUpdate(i.dataModelUpdate,i.dataModelUpdate.surfaceId),i.deleteSurface&&this.handleDeleteSurface(i.deleteSurface)}}getData(e,r,i=t.DEFAULT_SURFACE_ID){let o=this.getOrCreateSurface(i);if(!o)return null;let n;return r==="."||r===""?n=e.dataContextPath??"/":n=this.resolvePath(r,e.dataContextPath),this.getDataByPath(o.dataModel,n)}setData(e,r,i,o=t.DEFAULT_SURFACE_ID){if(!e){console.warn("No component node set");return}let n=this.getOrCreateSurface(o);if(!n)return;let p;r==="."||r===""?p=e.dataContextPath??"/":p=this.resolvePath(r,e.dataContextPath),this.setDataByPath(n.dataModel,p,i)}resolvePath(e,r){return e.startsWith("/")?e:r&&r!=="/"?r.endsWith("/")?`${r}${e}`:`${r}/${e}`:`/${e}`}parseIfJsonString(e){if(typeof e!="string")return e;let r=e.trim();if(r.startsWith("{")&&r.endsWith("}")||r.startsWith("[")&&r.endsWith("]"))try{return JSON.parse(e)}catch(i){return console.warn(`Failed to parse potential JSON string: "${e.substring(0,50)}..."`,i),e}return e}convertKeyValueArrayToMap(e){let r=new this.mapCtor;for(let i of e){if(!l(i)||!("key"in i))continue;let o=i.key,n=this.findValueKey(i);if(!n)continue;let p=i[n];n==="valueMap"&&Array.isArray(p)?p=this.convertKeyValueArrayToMap(p):typeof p=="string"&&(p=this.parseIfJsonString(p)),this.setDataByPath(r,o,p)}return r}setDataByPath(e,r,i){if(Array.isArray(i)&&(i.length===0||l(i[0])&&"key"in i[0]))if(i.length===1&&l(i[0])&&i[0].key==="."){let d=i[0],h=this.findValueKey(d);h?(i=d[h],h==="valueMap"&&Array.isArray(i)?i=this.convertKeyValueArrayToMap(i):typeof i=="string"&&(i=this.parseIfJsonString(i))):i=this.convertKeyValueArrayToMap(i)}else i=this.convertKeyValueArrayToMap(i);let o=this.normalizePath(r).split("/").filter(d=>d);if(o.length===0){if(i instanceof Map||l(i)){!(i instanceof Map)&&l(i)&&(i=new this.mapCtor(Object.entries(i))),e.clear();for(let[d,h]of i.entries())e.set(d,h)}else console.error("Cannot set root of DataModel to a non-Map value.");return}let n=e;for(let d=0;d<o.length-1;d++){let h=o[d],s;n instanceof Map?s=n.get(h):Array.isArray(n)&&/^\d+$/.test(h)&&(s=n[parseInt(h,10)]),(s===void 0||typeof s!="object"||s===null)&&(s=new this.mapCtor,n instanceof this.mapCtor?n.set(h,s):Array.isArray(n)&&(n[parseInt(h,10)]=s)),n=s}let p=o[o.length-1],c=i;n instanceof this.mapCtor?n.set(p,c):Array.isArray(n)&&/^\d+$/.test(p)&&(n[parseInt(p,10)]=c)}normalizePath(e){return"/"+e.replace(/\[(\d+)\]/g,".$1").split(".").filter(o=>o.length>0).join("/")}getDataByPath(e,r){let i=this.normalizePath(r).split("/").filter(n=>n),o=e;for(let n of i){if(o==null)return null;if(o instanceof Map)o=o.get(n);else if(Array.isArray(o)&&/^\d+$/.test(n))o=o[parseInt(n,10)];else if(l(o)){if(!Object.prototype.hasOwnProperty.call(o,n))return null;o=o[n]}else return null}return o}getOrCreateSurface(e){let r=this.surfaces.get(e);return r||(r=new this.objCtor({rootComponentId:null,componentTree:null,dataModel:new this.mapCtor,components:new this.mapCtor,styles:new this.objCtor}),this.surfaces.set(e,r)),r}handleBeginRendering(e,r){let i=this.getOrCreateSurface(r);i.rootComponentId=e.root,i.styles=e.styles??{},this.rebuildComponentTree(i)}handleSurfaceUpdate(e,r){let i=this.getOrCreateSurface(r);for(let o of e.components)i.components.set(o.id,o);this.rebuildComponentTree(i)}handleDataModelUpdate(e,r){let i=this.getOrCreateSurface(r),o=e.path??"/";this.setDataByPath(i.dataModel,o,e.contents),this.rebuildComponentTree(i)}handleDeleteSurface(e){this.surfaces.delete(e.surfaceId)}rebuildComponentTree(e){if(!e.rootComponentId){e.componentTree=null;return}let r=new this.setCtor;e.componentTree=this.buildNodeRecursive(e.rootComponentId,e,r,"/","")}findValueKey(e){return Object.keys(e).find(r=>r.startsWith("value"))}buildNodeRecursive(e,r,i,o,n=""){let p=`${e}${n}`,{components:c}=r;if(!c.has(e))return null;if(i.has(p))throw new I(`Circular dependency for component "${p}".`);i.add(p);let d=c.get(e),h=d.component??{},s=Object.keys(h)[0],w=h[s],a=new this.objCtor;if(l(w))for(let[T,C]of Object.entries(w))a[T]=this.resolvePropertyValue(C,r,i,o,n,T==="action");i.delete(p);let f={id:p,dataContextPath:o,weight:d.weight??"initial"};switch(s){case"Text":if(!G(a))throw new u(`Invalid data; expected ${s}`);return new this.objCtor({...f,type:"Text",properties:a});case"Image":if(!F(a))throw new u(`Invalid data; expected ${s}`);return new this.objCtor({...f,type:"Image",properties:a});case"Icon":if(!E(a))throw new u(`Invalid data; expected ${s}`);return new this.objCtor({...f,type:"Icon",properties:a});case"Video":if(!Y(a))throw new u(`Invalid data; expected ${s}`);return new this.objCtor({...f,type:"Video",properties:a});case"AudioPlayer":if(!D(a))throw new u(`Invalid data; expected ${s}`);return new this.objCtor({...f,type:"AudioPlayer",properties:a});case"Row":if(!K(a))throw new u(`Invalid data; expected ${s}`);return new this.objCtor({...f,type:"Row",properties:a});case"Column":if(!q(a))throw new u(`Invalid data; expected ${s}`);return new this.objCtor({...f,type:"Column",properties:a});case"List":if(!V(a))throw new u(`Invalid data; expected ${s}`);return new this.objCtor({...f,type:"List",properties:a});case"Card":if(!z(a))throw new u(`Invalid data; expected ${s}`);return new this.objCtor({...f,type:"Card",properties:a});case"Tabs":if(!H(a))throw new u(`Invalid data; expected ${s}`);return new this.objCtor({...f,type:"Tabs",properties:a});case"Divider":if(!B(a))throw new u(`Invalid data; expected ${s}`);return new this.objCtor({...f,type:"Divider",properties:a});case"Modal":if(!L(a))throw new u(`Invalid data; expected ${s}`);return new this.objCtor({...f,type:"Modal",properties:a});case"Button":if(!k(a))throw new u(`Invalid data; expected ${s}`);return new this.objCtor({...f,type:"Button",properties:a});case"CheckBox":if(!O(a))throw new u(`Invalid data; expected ${s}`);return new this.objCtor({...f,type:"CheckBox",properties:a});case"TextField":if(!J(a))throw new u(`Invalid data; expected ${s}`);return new this.objCtor({...f,type:"TextField",properties:a});case"DateTimeInput":if(!N(a))throw new u(`Invalid data; expected ${s}`);return new this.objCtor({...f,type:"DateTimeInput",properties:a});case"MultipleChoice":if(!_(a))throw new u(`Invalid data; expected ${s}`);return new this.objCtor({...f,type:"MultipleChoice",properties:a});case"Slider":if(!W(a))throw new u(`Invalid data; expected ${s}`);return new this.objCtor({...f,type:"Slider",properties:a});default:return new this.objCtor({...f,type:s,properties:a})}}resolvePropertyValue(e,r,i,o,n="",p=!1){if(!p&&typeof e=="string"&&r.components.has(e))return this.buildNodeRecursive(e,r,i,o,n);if(!p&&U(e)){if(e.explicitList)return e.explicitList.map(c=>this.buildNodeRecursive(c,r,i,o,n));if(e.template){let c=this.resolvePath(e.template.dataBinding,o),d=this.getDataByPath(r.dataModel,c),h=e.template;if(Array.isArray(d))return d.map((w,a)=>{let C=`:${[...o.split("/").filter(pe=>/^\d+$/.test(pe)),a].join(":")}`,le=`${c}/${a}`;return this.buildNodeRecursive(h.componentId,r,i,le,C)});let s=this.mapCtor;return d instanceof s?Array.from(d.keys(),w=>{let a=`:${w}`,f=`${c}/${w}`;return this.buildNodeRecursive(h.componentId,r,i,f,a)}):new this.arrayCtor}}if(Array.isArray(e))return e.map(c=>this.resolvePropertyValue(c,r,i,o,n,p));if(l(e)){let c=new this.objCtor;for(let[d,h]of Object.entries(e)){let s=h;if(M(d,h)&&o!=="/"){s=h.replace(/^\.?\/item/,"").replace(/^\.?\/text/,"").replace(/^\.?\/label/,"").replace(/^\.?\//,""),c[d]=s;continue}c[d]=this.resolvePropertyValue(s,r,i,o,n,p||d==="action")}return c}return e}};A.DEFAULT_SURFACE_ID="@default";var me=`
  &:not([disabled]) {
    cursor: pointer;
    opacity: var(--opacity, 0);
    transition: opacity var(--speed, 0.2s) cubic-bezier(0, 0, 0.3, 1);

    &:hover,
    &:focus {
      opacity: 1;
    }
  }`,Z=`
  ${new Array(21).fill(0).map((t,e)=>`.behavior-ho-${e*5} {
          --opacity: ${e/20};
          ${me}
        }`).join(`
`)}

  .behavior-o-s {
    overflow: scroll;
  }

  .behavior-o-a {
    overflow: auto;
  }

  .behavior-o-h {
    overflow: hidden;
  }

  .behavior-sw-n {
    scrollbar-width: none;
  }
`;var ee=`
  ${new Array(25).fill(0).map((t,e)=>`
        .border-bw-${e} { border-width: ${e}px; }
        .border-btw-${e} { border-top-width: ${e}px; }
        .border-bbw-${e} { border-bottom-width: ${e}px; }
        .border-blw-${e} { border-left-width: ${e}px; }
        .border-brw-${e} { border-right-width: ${e}px; }

        .border-ow-${e} { outline-width: ${e}px; }
        .border-br-${e} { border-radius: ${e*4}px; overflow: hidden;}`).join(`
`)}

  .border-br-50pc {
    border-radius: 50%;
  }

  .border-bs-s {
    border-style: solid;
  }
`;var S=[0,5,10,15,20,25,30,35,40,50,60,70,80,90,95,98,99,100];function ze(...t){let e={};for(let r of t)for(let[i,o]of Object.entries(r)){let n=i.split("-").with(-1,"").join("-"),p=Object.keys(e).filter(c=>c.startsWith(n));for(let c of p)delete e[c];e[i]=o}return e}function Oe(t,e,...r){let i=structuredClone(t);for(let o of r)for(let n of Object.keys(o)){let p=n.split("-").with(-1,"").join("-");for(let[c,d]of Object.entries(i)){if(e.includes(c))continue;let h=!1;for(let s=0;s<d.length;s++)d[s].startsWith(p)&&(h=!0,d[s]=n);h||d.push(n)}}return i}function qe(t){let e={};for(let r of Object.values(t))for(let[i,o]of Object.entries(r)){let n=m(i);e[n]=o}return e}function m(t){return t.startsWith("nv")?`--nv-${t.slice(2)}`:`--${t[0]}-${t.slice(1)}`}var v=t=>`
    ${t.map(e=>{let r=R(e);return`.color-bc-${e} { border-color: light-dark(var(${m(e)}), var(${m(r)})); }`}).join(`
`)}

    ${t.map(e=>{let r=R(e),i=[`.color-bgc-${e} { background-color: light-dark(var(${m(e)}), var(${m(r)})); }`,`.color-bbgc-${e}::backdrop { background-color: light-dark(var(${m(e)}), var(${m(r)})); }`];for(let o=.1;o<1;o+=.1)i.push(`.color-bbgc-${e}_${(o*100).toFixed(0)}::backdrop {
            background-color: light-dark(oklch(from var(${m(e)}) l c h / calc(alpha * ${o.toFixed(1)})), oklch(from var(${m(r)}) l c h / calc(alpha * ${o.toFixed(1)})) );
          }
        `);return i.join(`
`)}).join(`
`)}

  ${t.map(e=>{let r=R(e);return`.color-c-${e} { color: light-dark(var(${m(e)}), var(${m(r)})); }`}).join(`
`)}
  `,R=t=>{let e=t.match(/^([a-z]+)(\d+)$/);if(!e)return t;let[,r,i]=e,n=100-parseInt(i,10),p=S.reduce((c,d)=>Math.abs(d-n)<Math.abs(c-n)?d:c);return`${r}${p}`},j=t=>S.map(e=>`${t}${e}`),te=[v(j("p")),v(j("s")),v(j("t")),v(j("n")),v(j("nv")),v(j("e")),`
    .color-bgc-transparent {
      background-color: transparent;
    }

    :host {
      color-scheme: var(--color-scheme);
    }
  `];var re=`
  .g-icon {
    font-family: "Material Symbols Outlined", "Google Symbols";
    font-weight: normal;
    font-style: normal;
    font-display: optional;
    font-size: 24px;
    width: 1em;
    height: 1em;
    user-select: none;
    line-height: 1;
    letter-spacing: normal;
    text-transform: none;
    display: inline-block;
    white-space: nowrap;
    word-wrap: normal;
    direction: ltr;
    font-feature-settings: "liga";
    -webkit-font-feature-settings: "liga";
    -webkit-font-smoothing: antialiased;
    text-rendering: optimizeLegibility;
    -moz-osx-font-smoothing: grayscale;
    overflow: hidden;

    font-variation-settings: "FILL" 0, "wght" 300, "GRAD" 0, "opsz" 48,
      "ROND" 100;

    &.filled {
      font-variation-settings: "FILL" 1, "wght" 300, "GRAD" 0, "opsz" 48,
        "ROND" 100;
    }

    &.filled-heavy {
      font-variation-settings: "FILL" 1, "wght" 700, "GRAD" 0, "opsz" 48,
        "ROND" 100;
    }
  }
`;var ie=`
  :host {
    ${new Array(16).fill(0).map((t,e)=>`--g-${e+1}: ${(e+1)*4}px;`).join(`
`)}
  }

  ${new Array(49).fill(0).map((t,e)=>{let r=e-24,i=r<0?`n${Math.abs(r)}`:r.toString();return`
        .layout-p-${i} { --padding: ${r*4}px; padding: var(--padding); }
        .layout-pt-${i} { padding-top: ${r*4}px; }
        .layout-pr-${i} { padding-right: ${r*4}px; }
        .layout-pb-${i} { padding-bottom: ${r*4}px; }
        .layout-pl-${i} { padding-left: ${r*4}px; }

        .layout-m-${i} { --margin: ${r*4}px; margin: var(--margin); }
        .layout-mt-${i} { margin-top: ${r*4}px; }
        .layout-mr-${i} { margin-right: ${r*4}px; }
        .layout-mb-${i} { margin-bottom: ${r*4}px; }
        .layout-ml-${i} { margin-left: ${r*4}px; }

        .layout-t-${i} { top: ${r*4}px; }
        .layout-r-${i} { right: ${r*4}px; }
        .layout-b-${i} { bottom: ${r*4}px; }
        .layout-l-${i} { left: ${r*4}px; }`}).join(`
`)}

  ${new Array(25).fill(0).map((t,e)=>`
        .layout-g-${e} { gap: ${e*4}px; }`).join(`
`)}

  ${new Array(8).fill(0).map((t,e)=>`
        .layout-grd-col${e+1} { grid-template-columns: ${"1fr ".repeat(e+1).trim()}; }`).join(`
`)}

  .layout-pos-a {
    position: absolute;
  }

  .layout-pos-rel {
    position: relative;
  }

  .layout-dsp-none {
    display: none;
  }

  .layout-dsp-block {
    display: block;
  }

  .layout-dsp-grid {
    display: grid;
  }

  .layout-dsp-iflex {
    display: inline-flex;
  }

  .layout-dsp-flexvert {
    display: flex;
    flex-direction: column;
  }

  .layout-dsp-flexhor {
    display: flex;
    flex-direction: row;
  }

  .layout-fw-w {
    flex-wrap: wrap;
  }

  .layout-al-fs {
    align-items: start;
  }

  .layout-al-fe {
    align-items: end;
  }

  .layout-al-c {
    align-items: center;
  }

  .layout-as-n {
    align-self: normal;
  }

  .layout-js-c {
    justify-self: center;
  }

  .layout-sp-c {
    justify-content: center;
  }

  .layout-sp-ev {
    justify-content: space-evenly;
  }

  .layout-sp-bt {
    justify-content: space-between;
  }

  .layout-sp-s {
    justify-content: start;
  }

  .layout-sp-e {
    justify-content: end;
  }

  .layout-ji-e {
    justify-items: end;
  }

  .layout-r-none {
    resize: none;
  }

  .layout-fs-c {
    field-sizing: content;
  }

  .layout-fs-n {
    field-sizing: none;
  }

  .layout-flx-0 {
    flex: 0 0 auto;
  }

  .layout-flx-1 {
    flex: 1 0 auto;
  }

  .layout-c-s {
    contain: strict;
  }

  /** Widths **/

  ${new Array(10).fill(0).map((t,e)=>{let r=(e+1)*10;return`.layout-w-${r} { width: ${r}%; max-width: ${r}%; }`}).join(`
`)}

  ${new Array(16).fill(0).map((t,e)=>{let r=e*4;return`.layout-wp-${e} { width: ${r}px; }`}).join(`
`)}

  /** Heights **/

  ${new Array(10).fill(0).map((t,e)=>{let r=(e+1)*10;return`.layout-h-${r} { height: ${r}%; }`}).join(`
`)}

  ${new Array(16).fill(0).map((t,e)=>{let r=e*4;return`.layout-hp-${e} { height: ${r}px; }`}).join(`
`)}

  .layout-el-cv {
    & img,
    & video {
      width: 100%;
      height: 100%;
      object-fit: cover;
      margin: 0;
    }
  }

  .layout-ar-sq {
    aspect-ratio: 1 / 1;
  }

  .layout-ex-fb {
    margin: calc(var(--padding) * -1) 0 0 calc(var(--padding) * -1);
    width: calc(100% + var(--padding) * 2);
    height: calc(100% + var(--padding) * 2);
  }
`;var oe=`
  ${new Array(21).fill(0).map((t,e)=>`.opacity-el-${e*5} { opacity: ${e/20}; }`).join(`
`)}
`;var ne=`
  :host {
    --default-font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
    --default-font-family-mono: "Courier New", Courier, monospace;
  }

  .typography-f-s {
    font-family: var(--font-family, var(--default-font-family));
    font-optical-sizing: auto;
    font-variation-settings: "slnt" 0, "wdth" 100, "GRAD" 0;
  }

  .typography-f-sf {
    font-family: var(--font-family-flex, var(--default-font-family));
    font-optical-sizing: auto;
  }

  .typography-f-c {
    font-family: var(--font-family-mono, var(--default-font-family));
    font-optical-sizing: auto;
    font-variation-settings: "slnt" 0, "wdth" 100, "GRAD" 0;
  }

  .typography-v-r {
    font-variation-settings: "slnt" 0, "wdth" 100, "GRAD" 0, "ROND" 100;
  }

  .typography-ta-s {
    text-align: start;
  }

  .typography-ta-c {
    text-align: center;
  }

  .typography-fs-n {
    font-style: normal;
  }

  .typography-fs-i {
    font-style: italic;
  }

  .typography-sz-ls {
    font-size: 11px;
    line-height: 16px;
  }

  .typography-sz-lm {
    font-size: 12px;
    line-height: 16px;
  }

  .typography-sz-ll {
    font-size: 14px;
    line-height: 20px;
  }

  .typography-sz-bs {
    font-size: 12px;
    line-height: 16px;
  }

  .typography-sz-bm {
    font-size: 14px;
    line-height: 20px;
  }

  .typography-sz-bl {
    font-size: 16px;
    line-height: 24px;
  }

  .typography-sz-ts {
    font-size: 14px;
    line-height: 20px;
  }

  .typography-sz-tm {
    font-size: 16px;
    line-height: 24px;
  }

  .typography-sz-tl {
    font-size: 22px;
    line-height: 28px;
  }

  .typography-sz-hs {
    font-size: 24px;
    line-height: 32px;
  }

  .typography-sz-hm {
    font-size: 28px;
    line-height: 36px;
  }

  .typography-sz-hl {
    font-size: 32px;
    line-height: 40px;
  }

  .typography-sz-ds {
    font-size: 36px;
    line-height: 44px;
  }

  .typography-sz-dm {
    font-size: 45px;
    line-height: 52px;
  }

  .typography-sz-dl {
    font-size: 57px;
    line-height: 64px;
  }

  .typography-ws-p {
    white-space: pre-line;
  }

  .typography-ws-nw {
    white-space: nowrap;
  }

  .typography-td-none {
    text-decoration: none;
  }

  /** Weights **/

  ${new Array(9).fill(0).map((t,e)=>{let r=(e+1)*100;return`.typography-w-${r} { font-weight: ${r}; }`}).join(`
`)}
`;var et=[Z,ee,te,re,ie,oe,ne].flat(1/0).join(`
`);import{isSafeRegex as gt}from"/vendor/esm/@a2ui/web_core@0.15.0/X-ZGxpdEAzLjMuMw/es2022/src/v0_9/basic_catalog/functions/safe_regex.mjs";import{A2uiMessageSchema as wt}from"/vendor/esm/@a2ui/web_core@0.15.0/X-ZGxpdEAzLjMuMw/es2022/src/v0_8/schema/server-to-client.mjs";export*from"/vendor/esm/@a2ui/web_core@0.15.0/X-ZGxpdEAzLjMuMw/es2022/src/v0_8/standard_defs.mjs";var ae={title:"A2UI Message Schema",description:"Describes a JSON payload for an A2UI (Agent to UI) message, which is used to dynamically construct and update user interfaces. A message MUST contain exactly ONE of the action properties: 'beginRendering', 'surfaceUpdate', 'dataModelUpdate', or 'deleteSurface'.",type:"object",additionalProperties:!1,properties:{beginRendering:{type:"object",description:"Signals the client to begin rendering a surface with a root component and specific styles.",additionalProperties:!1,properties:{surfaceId:{type:"string",description:"The unique identifier for the UI surface to be rendered."},catalogId:{type:"string",description:"The identifier of the component catalog to use for this surface. If omitted, the client MUST default to the standard catalog for this A2UI version (https://a2ui.org/specification/v0_8/standard_catalog_definition.json)."},root:{type:"string",description:"The ID of the root component to render."},styles:{type:"object",description:"Styling information for the UI.",additionalProperties:!1,properties:{font:{type:"string",description:"The primary font for the UI."},primaryColor:{type:"string",description:"The primary UI color as a hexadecimal code (e.g., '#00BFFF').",pattern:"^#[0-9a-fA-F]{6}$"}}}},required:["root","surfaceId"]},surfaceUpdate:{type:"object",description:"Updates a surface with a new set of components.",additionalProperties:!1,properties:{surfaceId:{type:"string",description:"The unique identifier for the UI surface to be updated. If you are adding a new surface this *must* be a new, unique identified that has never been used for any existing surfaces shown."},components:{type:"array",description:"A list containing all UI components for the surface.",minItems:1,items:{type:"object",description:"Represents a *single* component in a UI widget tree. This component could be one of many supported types.",additionalProperties:!1,properties:{id:{type:"string",description:"The unique identifier for this component."},weight:{type:"number",description:"The relative weight of this component within a Row or Column. This corresponds to the CSS 'flex-grow' property. Note: this may ONLY be set when the component is a direct descendant of a Row or Column."},component:{type:"object",description:"A wrapper object that MUST contain exactly one key, which is the name of the component type (e.g., 'Heading'). The value is an object containing the properties for that specific component.",additionalProperties:!1,properties:{Text:{type:"object",additionalProperties:!1,properties:{text:{type:"object",description:"The text content to display. This can be a literal string or a reference to a value in the data model ('path', e.g., '/doc/title'). While simple Markdown formatting is supported (i.e. without HTML, images, or links), utilizing dedicated UI components is generally preferred for a richer and more structured presentation.",additionalProperties:!1,properties:{literalString:{type:"string"},path:{type:"string"}}},usageHint:{type:"string",description:"A hint for the base text style. One of:\n- `h1`: Largest heading.\n- `h2`: Second largest heading.\n- `h3`: Third largest heading.\n- `h4`: Fourth largest heading.\n- `h5`: Fifth largest heading.\n- `caption`: Small text for captions.\n- `body`: Standard body text.",enum:["h1","h2","h3","h4","h5","caption","body"]}},required:["text"]},Image:{type:"object",additionalProperties:!1,properties:{url:{type:"object",description:"The URL of the image to display. This can be a literal string ('literal') or a reference to a value in the data model ('path', e.g. '/thumbnail/url').",additionalProperties:!1,properties:{literalString:{type:"string"},path:{type:"string"}}},altText:{type:"object",description:"The alt text for the image. This can be a literal string ('literal') or a reference to a value in the data model ('path', e.g. '/thumbnail/altText').",additionalProperties:!1,properties:{literalString:{type:"string"},path:{type:"string"}}},fit:{type:"string",description:"Specifies how the image should be resized to fit its container. This corresponds to the CSS 'object-fit' property.",enum:["contain","cover","fill","none","scale-down"]},usageHint:{type:"string",description:"A hint for the image size and style. One of:\n- `icon`: Small square icon.\n- `avatar`: Circular avatar image.\n- `smallFeature`: Small feature image.\n- `mediumFeature`: Medium feature image.\n- `largeFeature`: Large feature image.\n- `header`: Full-width, full bleed, header image.",enum:["icon","avatar","smallFeature","mediumFeature","largeFeature","header"]}},required:["url"]},Icon:{type:"object",additionalProperties:!1,properties:{name:{type:"object",description:"The name of the icon to display. This can be a literal string or a reference to a value in the data model ('path', e.g. '/form/submit').",additionalProperties:!1,properties:{literalString:{type:"string",enum:["accountCircle","add","arrowBack","arrowForward","attachFile","calendarToday","call","camera","check","close","delete","download","edit","event","error","favorite","favoriteOff","folder","help","home","info","locationOn","lock","lockOpen","mail","menu","moreVert","moreHoriz","notificationsOff","notifications","payment","person","phone","photo","print","refresh","search","send","settings","share","shoppingCart","star","starHalf","starOff","upload","visibility","visibilityOff","warning"]},path:{type:"string"}}}},required:["name"]},Video:{type:"object",additionalProperties:!1,properties:{url:{type:"object",description:"The URL of the video to display. This can be a literal string or a reference to a value in the data model ('path', e.g. '/video/url').",additionalProperties:!1,properties:{literalString:{type:"string"},path:{type:"string"}}}},required:["url"]},AudioPlayer:{type:"object",additionalProperties:!1,properties:{url:{type:"object",description:"The URL of the audio to be played. This can be a literal string ('literal') or a reference to a value in the data model ('path', e.g. '/song/url').",additionalProperties:!1,properties:{literalString:{type:"string"},path:{type:"string"}}},description:{type:"object",description:"A description of the audio, such as a title or summary. This can be a literal string or a reference to a value in the data model ('path', e.g. '/song/title').",additionalProperties:!1,properties:{literalString:{type:"string"},path:{type:"string"}}}},required:["url"]},Row:{type:"object",additionalProperties:!1,properties:{children:{type:"object",description:"Defines the children. Use 'explicitList' for a fixed set of children, or 'template' to generate children from a data list.",additionalProperties:!1,properties:{explicitList:{type:"array",items:{type:"string"}},template:{type:"object",description:"A template for generating a dynamic list of children from a data model list. `componentId` is the component to use as a template, and `dataBinding` is the path to the map of components in the data model. Values in the map will define the list of children.",additionalProperties:!1,properties:{componentId:{type:"string"},dataBinding:{type:"string"}},required:["componentId","dataBinding"]}}},distribution:{type:"string",description:"Defines the arrangement of children along the main axis (horizontally). This corresponds to the CSS 'justify-content' property.",enum:["center","end","spaceAround","spaceBetween","spaceEvenly","start"]},alignment:{type:"string",description:"Defines the alignment of children along the cross axis (vertically). This corresponds to the CSS 'align-items' property.",enum:["start","center","end","stretch"]}},required:["children"]},Column:{type:"object",additionalProperties:!1,properties:{children:{type:"object",description:"Defines the children. Use 'explicitList' for a fixed set of children, or 'template' to generate children from a data list.",additionalProperties:!1,properties:{explicitList:{type:"array",items:{type:"string"}},template:{type:"object",description:"A template for generating a dynamic list of children from a data model list. `componentId` is the component to use as a template, and `dataBinding` is the path to the map of components in the data model. Values in the map will define the list of children.",additionalProperties:!1,properties:{componentId:{type:"string"},dataBinding:{type:"string"}},required:["componentId","dataBinding"]}}},distribution:{type:"string",description:"Defines the arrangement of children along the main axis (vertically). This corresponds to the CSS 'justify-content' property.",enum:["start","center","end","spaceBetween","spaceAround","spaceEvenly"]},alignment:{type:"string",description:"Defines the alignment of children along the cross axis (horizontally). This corresponds to the CSS 'align-items' property.",enum:["center","end","start","stretch"]}},required:["children"]},List:{type:"object",additionalProperties:!1,properties:{children:{type:"object",description:"Defines the children. Use 'explicitList' for a fixed set of children, or 'template' to generate children from a data list.",additionalProperties:!1,properties:{explicitList:{type:"array",items:{type:"string"}},template:{type:"object",description:"A template for generating a dynamic list of children from a data model list. `componentId` is the component to use as a template, and `dataBinding` is the path to the map of components in the data model. Values in the map will define the list of children.",additionalProperties:!1,properties:{componentId:{type:"string"},dataBinding:{type:"string"}},required:["componentId","dataBinding"]}}},direction:{type:"string",description:"The direction in which the list items are laid out.",enum:["vertical","horizontal"]},alignment:{type:"string",description:"Defines the alignment of children along the cross axis.",enum:["start","center","end","stretch"]}},required:["children"]},Card:{type:"object",additionalProperties:!1,properties:{child:{type:"string",description:"The ID of the component to be rendered inside the card."}},required:["child"]},Tabs:{type:"object",additionalProperties:!1,properties:{tabItems:{type:"array",description:"An array of objects, where each object defines a tab with a title and a child component.",items:{type:"object",additionalProperties:!1,properties:{title:{type:"object",description:"The tab title. Defines the value as either a literal value or a path to data model value (e.g. '/options/title').",additionalProperties:!1,properties:{literalString:{type:"string"},path:{type:"string"}}},child:{type:"string"}},required:["title","child"]}}},required:["tabItems"]},Divider:{type:"object",additionalProperties:!1,properties:{axis:{type:"string",description:"The orientation of the divider.",enum:["horizontal","vertical"]}}},Modal:{type:"object",additionalProperties:!1,properties:{entryPointChild:{type:"string",description:"The ID of the component that opens the modal when interacted with (e.g., a button)."},contentChild:{type:"string",description:"The ID of the component to be displayed inside the modal."}},required:["entryPointChild","contentChild"]},Button:{type:"object",additionalProperties:!1,properties:{child:{type:"string",description:"The ID of the component to display in the button, typically a Text component."},primary:{type:"boolean",description:"Indicates if this button should be styled as the primary action."},action:{type:"object",description:"The client-side action to be dispatched when the button is clicked. It includes the action's name and an optional context payload.",additionalProperties:!1,properties:{name:{type:"string"},context:{type:"array",items:{type:"object",additionalProperties:!1,properties:{key:{type:"string"},value:{type:"object",description:"Defines the value to be included in the context as either a literal value or a path to a data model value (e.g. '/user/name').",additionalProperties:!1,properties:{path:{type:"string"},literalString:{type:"string"},literalNumber:{type:"number"},literalBoolean:{type:"boolean"}}}},required:["key","value"]}}},required:["name"]}},required:["child","action"]},CheckBox:{type:"object",additionalProperties:!1,properties:{label:{type:"object",description:"The text to display next to the checkbox. Defines the value as either a literal value or a path to data model ('path', e.g. '/option/label').",additionalProperties:!1,properties:{literalString:{type:"string"},path:{type:"string"}}},value:{type:"object",description:"The current state of the checkbox (true for checked, false for unchecked). This can be a literal boolean ('literalBoolean') or a reference to a value in the data model ('path', e.g. '/filter/open').",additionalProperties:!1,properties:{literalBoolean:{type:"boolean"},path:{type:"string"}}}},required:["label","value"]},TextField:{type:"object",additionalProperties:!1,properties:{label:{type:"object",description:"The text label for the input field. This can be a literal string or a reference to a value in the data model ('path, e.g. '/user/name').",additionalProperties:!1,properties:{literalString:{type:"string"},path:{type:"string"}}},text:{type:"object",description:"The value of the text field. This can be a literal string or a reference to a value in the data model ('path', e.g. '/user/name').",additionalProperties:!1,properties:{literalString:{type:"string"},path:{type:"string"}}},textFieldType:{type:"string",description:"The type of input field to display.",enum:["date","longText","number","shortText","obscured"]},validationRegexp:{type:"string",description:"A regular expression used for client-side validation of the input."}},required:["label"]},DateTimeInput:{type:"object",additionalProperties:!1,properties:{value:{type:"object",description:"The selected date and/or time value in ISO 8601 format. This can be a literal string ('literalString') or a reference to a value in the data model ('path', e.g. '/user/dob').",additionalProperties:!1,properties:{literalString:{type:"string"},path:{type:"string"}}},enableDate:{type:"boolean",description:"If true, allows the user to select a date."},enableTime:{type:"boolean",description:"If true, allows the user to select a time."}},required:["value"]},MultipleChoice:{type:"object",additionalProperties:!1,properties:{selections:{type:"object",description:"The currently selected values for the component. This can be a literal array of strings or a path to an array in the data model('path', e.g. '/hotel/options').",additionalProperties:!1,properties:{literalArray:{type:"array",items:{type:"string"}},path:{type:"string"}}},options:{type:"array",description:"An array of available options for the user to choose from.",items:{type:"object",additionalProperties:!1,properties:{label:{type:"object",description:"The text to display for this option. This can be a literal string or a reference to a value in the data model (e.g. '/option/label').",additionalProperties:!1,properties:{literalString:{type:"string"},path:{type:"string"}}},value:{type:"string",description:"The value to be associated with this option when selected."}},required:["label","value"]}},maxAllowedSelections:{type:"integer",description:"The maximum number of options that the user is allowed to select."}},required:["selections","options"]},Slider:{type:"object",additionalProperties:!1,properties:{label:{type:"object",description:"The label for the slider. This can be a literal string or a reference to a value in the data model ('path').",additionalProperties:!1,properties:{literalString:{type:"string"},path:{type:"string"}}},value:{type:"object",description:"The current value of the slider. This can be a literal number ('literalNumber') or a reference to a value in the data model ('path', e.g. '/restaurant/cost').",additionalProperties:!1,properties:{literalNumber:{type:"number"},path:{type:"string"}}},minValue:{type:"number",description:"The minimum value of the slider."},maxValue:{type:"number",description:"The maximum value of the slider."}},required:["value"]}}}},required:["id","component"]}}},required:["surfaceId","components"]},dataModelUpdate:{type:"object",description:"Updates the data model for a surface.",additionalProperties:!1,properties:{surfaceId:{type:"string",description:"The unique identifier for the UI surface this data model update applies to."},path:{type:"string",description:"An optional path to a location within the data model (e.g., '/user/name'). If omitted, or set to '/', the entire data model will be replaced."},contents:{type:"array",description:"An array of data entries. Each entry must contain a 'key' and exactly one corresponding typed 'value*' property.",items:{type:"object",description:"A single data entry. Exactly one 'value*' property should be provided alongside the key.",additionalProperties:!1,properties:{key:{type:"string",description:"The key for this data entry."},valueString:{type:"string"},valueNumber:{type:"number"},valueBoolean:{type:"boolean"},valueMap:{type:"array",description:"Represents a map as an adjacency list.",items:{type:"object",description:"One entry in the map. Exactly one 'value*' property should be provided alongside the key.",additionalProperties:!1,properties:{key:{type:"string"},valueString:{type:"string"},valueNumber:{type:"number"},valueBoolean:{type:"boolean"}},required:["key"]}}},required:["key"]}}},required:["contents","surfaceId"]},deleteSurface:{type:"object",description:"Signals the client to delete the surface identified by 'surfaceId'.",additionalProperties:!1,properties:{surfaceId:{type:"string",description:"The unique identifier for the UI surface to be deleted."}},required:["surfaceId"]}}};var se={title:"A2UI Message Schema",description:"Describes a JSON payload for an A2UI (Agent to UI) message, which is used to dynamically construct and update user interfaces. A message MUST contain exactly ONE of the action properties: 'beginRendering', 'surfaceUpdate', 'dataModelUpdate', or 'deleteSurface'.",type:"object",additionalProperties:!1,properties:{beginRendering:{type:"object",description:"Signals the client to begin rendering a surface with a root component and specific styles.",additionalProperties:!1,properties:{surfaceId:{type:"string",description:"The unique identifier for the UI surface to be rendered."},catalogId:{type:"string",description:"The identifier of the component catalog to use for this surface. If omitted, the client MUST default to the standard catalog for this A2UI version (https://a2ui.org/specification/v0_8/standard_catalog_definition.json)."},root:{type:"string",description:"The ID of the root component to render."},styles:{type:"object",description:"Styling information for the UI.",additionalProperties:!0}},required:["root","surfaceId"]},surfaceUpdate:{type:"object",description:"Updates a surface with a new set of components.",additionalProperties:!1,properties:{surfaceId:{type:"string",description:"The unique identifier for the UI surface to be updated. If you are adding a new surface this *must* be a new, unique identified that has never been used for any existing surfaces shown."},components:{type:"array",description:"A list containing all UI components for the surface.",minItems:1,items:{type:"object",description:"Represents a *single* component in a UI widget tree. This component could be one of many supported types.",additionalProperties:!1,properties:{id:{type:"string",description:"The unique identifier for this component."},weight:{type:"number",description:"The relative weight of this component within a Row or Column. This corresponds to the CSS 'flex-grow' property. Note: this may ONLY be set when the component is a direct descendant of a Row or Column."},component:{type:"object",description:"A wrapper object that MUST contain exactly one key, which is the name of the component type (e.g., 'Heading'). The value is an object containing the properties for that specific component.",additionalProperties:!0}},required:["id","component"]}}},required:["surfaceId","components"]},dataModelUpdate:{type:"object",description:"Updates the data model for a surface.",additionalProperties:!1,properties:{surfaceId:{type:"string",description:"The unique identifier for the UI surface this data model update applies to."},path:{type:"string",description:"An optional path to a location within the data model (e.g., '/user/name'). If omitted, or set to '/', the entire data model will be replaced."},contents:{type:"array",description:"An array of data entries. Each entry must contain a 'key' and exactly one corresponding typed 'value*' property.",items:{type:"object",description:"A single data entry. Exactly one 'value*' property should be provided alongside the key.",additionalProperties:!1,properties:{key:{type:"string",description:"The key for this data entry."},valueString:{type:"string"},valueNumber:{type:"number"},valueBoolean:{type:"boolean"},valueMap:{type:"array",description:"Represents a map as an adjacency list.",items:{type:"object",description:"One entry in the map. Exactly one 'value*' property should be provided alongside the key.",additionalProperties:!1,properties:{key:{type:"string"},valueString:{type:"string"},valueNumber:{type:"number"},valueBoolean:{type:"boolean"}},required:["key"]}}},required:["key"]}}},required:["contents","surfaceId"]},deleteSurface:{type:"object",description:"Signals the client to delete the surface identified by 'surfaceId'.",additionalProperties:!1,properties:{surfaceId:{type:"string",description:"The unique identifier for the UI surface to be deleted."}},required:["surfaceId"]}}};var st={A2UIClientEventMessage:ae,A2uiMessageSchemaRaw:se};export{X as A2uiDataError,x as A2uiError,Q as A2uiExpressionError,A as A2uiMessageProcessor,wt as A2uiMessageSchema,I as A2uiStateError,u as A2uiValidationError,P as Events,st as Schemas,Oe as appendToAll,qe as createThemeStyles,U as isComponentArrayReference,l as isObject,M as isPath,D as isResolvedAudioPlayer,k as isResolvedButton,z as isResolvedCard,O as isResolvedCheckbox,q as isResolvedColumn,N as isResolvedDateTimeInput,B as isResolvedDivider,E as isResolvedIcon,F as isResolvedImage,V as isResolvedList,L as isResolvedModal,_ as isResolvedMultipleChoice,K as isResolvedRow,W as isResolvedSlider,H as isResolvedTabs,G as isResolvedText,J as isResolvedTextField,Y as isResolvedVideo,gt as isSafeRegex,$e as isValueMap,ze as merge,S as shades,et as structuralStyles,m as toProp};
//# sourceMappingURL=v0_8.mjs.map