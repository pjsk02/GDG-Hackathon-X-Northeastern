/* esm.sh - @a2ui/web_core@0.15.0/src/catalog/exclusive_union */
import{z as r}from"/vendor/esm/zod@_3.25.76__784fb81524.js";import{ignoreOverride as d,parseDef as a}from"/vendor/esm/zod-to-json-schema@_3.25.2__784fb81524.js";var u=new WeakSet;function m(e){let o=r.any().superRefine((n,s)=>{let i=0;for(let t of e)if(t.safeParse(n).success&&++i>1){s.addIssue({code:r.ZodIssueCode.custom,message:"Value matched more than one schema in oneOf"});return}});return u.add(o._def),o.pipe(r.union(e))}var h=(e,o)=>{let n=e;if(!n.in||!n.out||!u.has(n.in._def))return d;let i=n.out._def.options.map((t,c)=>a(t._def,{...o,currentPath:[...o.currentPath,"oneOf",`${c}`]})).filter(t=>t!==void 0);return e.description===void 0?{oneOf:i}:{oneOf:i,description:e.description}};export{m as exclusiveUnion,h as exclusiveUnionOverride};
/*! Bundled license information:

@a2ui/web_core/src/catalog/exclusive_union.js:
  (*
   * @license
   * Copyright 2024 Google LLC
   *
   * Licensed under the Apache License, Version 2.0 (the "License");
   * you may not use this file except in compliance with the License.
   * You may obtain a copy of the License at
   *
   *   https://www.apache.org/licenses/LICENSE-2.0
   *
   * Unless required by applicable law or agreed to in writing, software
   * distributed under the License is distributed on an "AS IS" BASIS,
   * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   * See the License for the specific language governing permissions and
   * limitations under the License.
   *)
*/
//# sourceMappingURL=exclusive_union.mjs.map