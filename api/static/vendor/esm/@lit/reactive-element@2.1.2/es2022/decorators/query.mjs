/* esm.sh - @lit/reactive-element@2.1.2/decorators/query */
import{desc as n}from"/vendor/esm/@lit/reactive-element@2.1.2/es2022/decorators/base.mjs";function d(u,i){return(e,r,l)=>{let s=o=>o.renderRoot?.querySelector(u)??null;if(i){let{get:o,set:c}=typeof r=="object"?e:l??(()=>{let t=Symbol();return{get(){return this[t]},set(h){this[t]=h}}})();return n(e,r,{get(){let t=o.call(this);return t===void 0&&(t=s(this),(t!==null||this.hasUpdated)&&c.call(this,t)),t}})}return n(e,r,{get(){return s(this)}})}}export{d as query};
/*! Bundled license information:

@lit/reactive-element/decorators/query.js:
  (**
   * @license
   * Copyright 2017 Google LLC
   * SPDX-License-Identifier: BSD-3-Clause
   *)
*/
//# sourceMappingURL=query.mjs.map