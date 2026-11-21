/* esm.sh - @lit/reactive-element@2.1.2/decorators/query-async */
import{desc as n}from"/vendor/esm/@lit/reactive-element@2.1.2/es2022/decorators/base.mjs";function s(e){return(t,r)=>n(t,r,{async get(){return await this.updateComplete,this.renderRoot?.querySelector(e)??null}})}export{s as queryAsync};
/*! Bundled license information:

@lit/reactive-element/decorators/query-async.js:
  (**
   * @license
   * Copyright 2017 Google LLC
   * SPDX-License-Identifier: BSD-3-Clause
   *)
*/
//# sourceMappingURL=query-async.mjs.map