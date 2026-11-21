/* esm.sh - @a2ui/web_core@0.15.0/catalogs/basic/v1 */
import{toWebComponentImplementation as n}from"/vendor/esm/@a2ui/web_core@0.15.0/X-ZGxpdEAzLjMuMw/es2022/src/universal/to_web_component_implementation.mjs";import{A2uiAudioPlayerElement as de,A2uiBasicButtonElement as he,A2uiBasicColumnElement as ue,A2uiBasicRowElement as fe,A2uiBasicTextElement as be,A2uiBasicTextFieldElement as Ae,A2uiCardElement as ge,A2uiCheckBoxElement as xe,A2uiChoicePickerElement as ye,A2uiDateTimeInputElement as Ce,A2uiDividerElement as Ie,A2uiIconElement as Te,A2uiImageElement as Fe,A2uiListElement as Se,A2uiModalElement as ve,A2uiSliderElement as De,A2uiTabsElement as we,A2uiVideoElement as Ee}from"/vendor/esm/@a2ui/web_core@0.15.0/X-ZGxpdEAzLjMuMw/es2022/src/universal/basic_catalog/components/index.mjs";import{z as e}from"/vendor/esm/zod@_3.25.76__784fb81524.js";import{spec as t,specDef as ae}from"/vendor/esm/@a2ui/web_core@0.15.0/X-ZGxpdEAzLjMuMw/es2022/src/catalog/spec_annotations.mjs";import{ActionSchema as re,CheckRuleSchema as r,ChildListSchema as D,ChildSchema as s,DataBindingSchema as se,DynamicBooleanSchema as ce,DynamicNumberSchema as le,DynamicStringListSchema as me,DynamicStringSchema as i}from"/vendor/esm/@a2ui/web_core@0.15.0/X-ZGxpdEAzLjMuMw/es2022/src/v1_0/schema/common-types.mjs";var o=ae("Weight",e.number().describe("The relative weight of this component within a Row or Column. This is similar to the CSS 'flex-grow' property. Note: this may ONLY be set when the component is a direct descendant of a Row or Column.")),l={name:"Text",schema:t(e.object({text:i.describe("REF:#/$defs/DynamicString|The text content to display. While simple Markdown formatting is supported (i.e. without HTML, images, or links), utilizing dedicated UI components is generally preferred for a richer and more structured presentation."),variant:e.enum(["caption","body"]).default("body").describe("A hint for the base text style.").optional(),weight:o.optional()}).strict(),{mixins:[]})},m={name:"Image",schema:t(e.object({url:i.describe("REF:#/$defs/DynamicString|The URL of the image to display."),description:i.describe("REF:#/$defs/DynamicString|Accessibility text for the image.").optional(),fit:e.enum(["contain","cover","fill","none","scaleDown"]).default("fill").describe("Specifies how the image should be resized to fit its container. This corresponds to the CSS 'object-fit' property.").optional(),variant:e.enum(["icon","avatar","smallFeature","mediumFeature","largeFeature","header"]).default("mediumFeature").describe("A hint for the image size and style.").optional(),weight:o.optional()}).strict(),{mixins:[]})},p={name:"Icon",schema:t(e.object({name:e.union([e.enum(["accountCircle","add","arrowBack","arrowForward","attachFile","calendarToday","call","camera","check","close","delete","download","edit","event","error","fastForward","favorite","favoriteOff","folder","help","home","info","locationOn","lock","lockOpen","mail","menu","moreVert","moreHoriz","notificationsOff","notifications","pause","payment","person","phone","photo","play","print","refresh","rewind","search","send","settings","share","shoppingCart","skipNext","skipPrevious","star","starHalf","starOff","stop","upload","visibility","visibilityOff","volumeDown","volumeMute","volumeOff","volumeUp","warning"]),t(e.object({svgPath:i.describe("REF:#/$defs/DynamicString")}),{closure:"additionalProperties"}),se.describe("REF:#/$defs/DataBinding")]).describe("The name of the icon to display."),weight:o.optional()}).strict(),{mixins:[]})},d={name:"Video",schema:t(e.object({url:i.describe("REF:#/$defs/DynamicString|The URL of the video to display."),posterUrl:i.describe("REF:#/$defs/DynamicString|The URL of the poster image to display before the video plays.").optional(),weight:o.optional()}).strict(),{mixins:[]})},h={name:"AudioPlayer",schema:t(e.object({url:i.describe("REF:#/$defs/DynamicString|The URL of the audio to be played."),description:i.describe("REF:#/$defs/DynamicString|A description of the audio, such as a title or summary.").optional(),weight:o.optional()}).strict(),{mixins:[]})},u={name:"Row",schema:t(e.object({children:D.describe("REF:#/$defs/ChildList|Defines the children. Use an array of strings for a fixed set of children, or a template object to generate children from a data list. Children cannot be defined inline, they must be referred to by ID."),justify:e.enum(["center","end","spaceAround","spaceBetween","spaceEvenly","start","stretch"]).default("start").describe("Defines the arrangement of children along the main axis (horizontally). Use 'spaceBetween' to push items to the edges, or 'start'/'end'/'center' to pack them together.").optional(),align:e.enum(["start","center","end","stretch"]).default("stretch").describe("Defines the alignment of children along the cross axis (vertically). This is similar to the CSS 'align-items' property, but uses camelCase values (e.g., 'start').").optional(),weight:o.optional()}).describe("A layout component that arranges its children horizontally. To create a grid layout, nest Columns within this Row.").strict(),{mixins:[]})},f={name:"Column",schema:t(e.object({children:D.describe("REF:#/$defs/ChildList|Defines the children. Use an array of strings for a fixed set of children, or a template object to generate children from a data list. Children cannot be defined inline, they must be referred to by ID."),justify:e.enum(["start","center","end","spaceBetween","spaceAround","spaceEvenly","stretch"]).default("start").describe("Defines the arrangement of children along the main axis (vertically). Use 'spaceBetween' to push items to the edges (e.g. header at top, footer at bottom), or 'start'/'end'/'center' to pack them together.").optional(),align:e.enum(["center","end","start","stretch"]).default("stretch").describe("Defines the alignment of children along the cross axis (horizontally). This is similar to the CSS 'align-items' property.").optional(),weight:o.optional()}).describe("A layout component that arranges its children vertically. To create a grid layout, nest Rows within this Column.").strict(),{mixins:[]})},b={name:"List",schema:t(e.object({children:D.describe("REF:#/$defs/ChildList|Defines the children. Use an array of strings for a fixed set of children, or a template object to generate children from a data list."),direction:e.enum(["vertical","horizontal"]).default("vertical").describe("The direction in which the list items are laid out.").optional(),align:e.enum(["start","center","end","stretch"]).default("stretch").describe("Defines the alignment of children along the cross axis.").optional(),weight:o.optional()}).strict(),{mixins:[]})},A={name:"Card",schema:t(e.object({child:s.describe("REF:#/$defs/Child|The ID of the single child component to be rendered inside the card. To display multiple elements, you MUST wrap them in a layout component (like Column or Row) and pass that container's ID here. Do NOT pass multiple IDs or a non-existent ID."),weight:o.optional()}).strict(),{mixins:[]})},g={name:"Tabs",schema:t(e.object({tabs:e.array(t(e.object({title:i.describe("REF:#/$defs/DynamicString|The tab title."),child:s.describe("REF:#/$defs/Child|The ID of the child component.")}),{closure:"additionalProperties"})).min(1).describe("An array of objects, where each object defines a tab with a title and a child component."),weight:o.optional()}).strict(),{mixins:[]})},x={name:"Modal",schema:t(e.object({trigger:s.describe("REF:#/$defs/Child|The ID of the component that opens the modal when interacted with (e.g., a button)."),content:s.describe("REF:#/$defs/Child|The ID of the component to be displayed inside the modal."),weight:o.optional()}).strict(),{mixins:[]})},y={name:"Divider",schema:t(e.object({axis:e.enum(["horizontal","vertical"]).default("horizontal").describe("The orientation of the divider.").optional(),weight:o.optional()}).strict(),{mixins:[]})},C={name:"Button",schema:t(e.object({checks:e.array(r.describe("REF:#/$defs/CheckRule")).describe("A list of validation check rules to perform on the component.").optional(),child:s.describe("REF:#/$defs/Child|The ID of the child component. Use a 'Text' component for a labeled button. Only use an 'Icon' if the requirements explicitly ask for an icon-only button."),variant:e.enum(["default","primary","borderless"]).default("default").describe("A hint for the button style. If omitted, a default button style is used. 'primary' indicates this is the main call-to-action button. 'borderless' means the button has no visual border or background, making its child content appear like a clickable link.").optional(),action:re.describe("REF:#/$defs/Action"),weight:o.optional()}).strict(),{mixins:["Checkable"]})},I={name:"TextField",schema:t(e.object({checks:e.array(r.describe("REF:#/$defs/CheckRule")).describe("A list of validation check rules to perform on the component.").optional(),label:i.describe("REF:#/$defs/DynamicString|The text label for the input field."),value:i.describe("REF:#/$defs/DynamicString|The value of the text field.").optional(),placeholder:i.describe("REF:#/$defs/DynamicString|The placeholder text for the input field.").optional(),variant:e.enum(["longText","number","shortText","obscured"]).default("shortText").describe("The type of input field to display.").optional(),weight:o.optional()}).strict(),{mixins:["Checkable"]})},T={name:"CheckBox",schema:t(e.object({checks:e.array(r.describe("REF:#/$defs/CheckRule")).describe("A list of validation check rules to perform on the component.").optional(),label:i.describe("REF:#/$defs/DynamicString|The text to display next to the checkbox."),value:ce.describe("REF:#/$defs/DynamicBoolean|The current state of the checkbox (true for checked, false for unchecked)."),weight:o.optional()}).strict(),{mixins:["Checkable"]})},F={name:"ChoicePicker",schema:t(e.object({checks:e.array(r.describe("REF:#/$defs/CheckRule")).describe("A list of validation check rules to perform on the component.").optional(),label:i.describe("REF:#/$defs/DynamicString|The label for the group of options.").optional(),variant:e.enum(["multipleSelection","mutuallyExclusive"]).default("mutuallyExclusive").describe("A hint for how the choice picker should be displayed and behave.").optional(),options:e.array(t(e.object({label:i.describe("REF:#/$defs/DynamicString|The text to display for this option."),value:e.string().describe("The stable value associated with this option.")}),{closure:"additionalProperties"})).describe("The list of available options to choose from."),value:me.describe("REF:#/$defs/DynamicStringList|The list of currently selected values. This should be bound to a string array in the data model."),displayStyle:e.enum(["checkbox","chips"]).default("checkbox").describe("The display style of the component.").optional(),filterable:e.boolean().default(!1).describe("If true, displays a search input to filter the options.").optional(),weight:o.optional()}).describe("A component that allows selecting one or more options from a list.").strict(),{mixins:["Checkable"]})},S={name:"Slider",schema:t(e.object({checks:e.array(r.describe("REF:#/$defs/CheckRule")).describe("A list of validation check rules to perform on the component.").optional(),label:i.describe("REF:#/$defs/DynamicString|The label for the slider.").optional(),min:e.number().default(0).describe("The minimum value of the slider.").optional(),max:e.number().describe("The maximum value of the slider."),value:le.describe("REF:#/$defs/DynamicNumber|The current value of the slider."),steps:t(e.number().int().describe("The number of discrete divisions in the slider range. If specified, the slider will snap to discrete values."),{keywords:{minimum:1}}).optional(),weight:o.optional()}).strict(),{mixins:["Checkable"],required:["value","max"]})},v={name:"DateTimeInput",schema:t(e.object({checks:e.array(r.describe("REF:#/$defs/CheckRule")).describe("A list of validation check rules to perform on the component.").optional(),value:i.describe("REF:#/$defs/DynamicString|The selected date and/or time value in ISO 8601 format. If not yet set, initialize with an empty string."),enableDate:e.boolean().default(!1).describe("If true, allows the user to select a date.").optional(),enableTime:e.boolean().default(!1).describe("If true, allows the user to select a time.").optional(),min:t(i.describe("REF:#/$defs/DynamicString|The minimum allowed date/time in ISO 8601 format."),{allOf:[{if:{type:"string"},then:{oneOf:[{format:"date"},{format:"time"},{format:"date-time"}]}}]}).optional(),max:t(i.describe("REF:#/$defs/DynamicString|The maximum allowed date/time in ISO 8601 format."),{allOf:[{if:{type:"string"},then:{oneOf:[{format:"date"},{format:"time"},{format:"date-time"}]}}]}).optional(),label:i.describe("REF:#/$defs/DynamicString|The text label for the input field.").optional(),weight:o.optional()}).strict(),{mixins:["Checkable"]})},pe=[l,m,p,d,h,u,f,b,A,g,x,y,C,I,T,F,S,v],B={schemaUri:"https://json-schema.org/draft/2020-12/schema",schemaId:"https://a2ui.org/specification/v1_0/catalogs/basic/catalog.json",title:"A2UI Basic Catalog",description:"Unified catalog of basic A2UI components and functions.",instructions:`For layout, use the Row and Column components to organize other components.

## Catalog Guidelines

1. String Concatenation & Formatting: A2UI does not support binary operators like '+' or formatting symbols. To concatenate strings or dynamically inject data bindings into text, you must use the catalog function \`formatString(value)\` where the value string contains placeholders formatted as \`\${expression}\`:
   formatString("Hello \${/user/name}")

2. Strict Hierarchy: You must strictly adhere to the requested component nesting and hierarchy. If the prompt specifies that a component is 'inside' or 'contained in' another component, you MUST place it as a child of that specific component, not as a sibling or in a different container.

3. Validation Checks: When components support validation checks, specify any custom error messages directly as the 'message' inside the check. Do NOT create separate text-display components to display validation errors.

## Examples

Example 1: Dynamic text form
\`\`\`json
[
  {
    "version": "1.0",
    "createSurface": {
      "surfaceId": "main",
      "catalogId": "https://a2ui.org/specification/v1_0/catalogs/basic/catalog.json",
      "components": [
        {
          "id": "root",
          "component": "Column",
          "children": ["repField", "valueField"]
        },
        {
          "id": "repField",
          "component": "TextField",
          "label": "Representative",
          "value": {"@path": "/form/rep"},
          "placeholder": "Enter name"
        },
        {
          "id": "valueField",
          "component": "TextField",
          "label": "Deal Value",
          "value": {"@path": "/form/value"},
          "placeholder": "0.00",
          "variant": "number",
          "checks": [
            {
              "condition": {
                "@call": "required",
                "args": {"value": {"@path": "/form/value"}}
              },
              "message": "Deal value is required."
            }
          ]
        }
      ],
      "dataModel": {
        "form": {
          "rep": "John Doe",
          "value": 1500.00
        }
      }
    }
  }
]
\`\`\`

Example 2: Dynamic list with templates
\`\`\`json
[
  {
    "version": "1.0",
    "createSurface": {
      "surfaceId": "main",
      "catalogId": "https://a2ui.org/specification/v1_0/catalogs/basic/catalog.json",
      "components": [
        {
          "id": "root",
          "component": "Card",
          "child": "breedList"
        },
        {
          "id": "breedList",
          "component": "List",
          "children": {
            "path": "/breeds",
            "componentId": "breedTemplate"
          },
          "direction": "horizontal"
        },
        {
          "id": "breedTemplate",
          "component": "Image",
          "url": {"@path": "url"}
        }
      ],
      "dataModel": {
        "breeds": [
          {
            "url": "https://example.com/poodle.jpg"
          },
          {
            "url": "https://example.com/lab.jpg"
          }
        ]
      }
    }
  }
]
\`\`\``,declaredProtocolVersion:"1.0",commonTypesUri:"common_types.json"};var j=n(de,h),$=n(he,C),P=n(ge,A),U=n(xe,T),L=n(ye,F),_=n(ue,f),z=n(Ce,v),M=n(Ie,y),V=n(Te,p),q=n(Fe,m),W=n(Se,b),H=n(ve,x),G=n(fe,u),Y=n(De,S),J=n(we,g),K=n(be,l),Q=n(Ae,I),X=n(Ee,d);import{V10_VALIDATION_FUNCTION_IMPLEMENTATIONS as ke}from"/vendor/esm/@a2ui/web_core@0.15.0/X-ZGxpdEAzLjMuMw/es2022/src/v1_0/functions/validation_functions.mjs";import{IndexImplementation as Re}from"/vendor/esm/@a2ui/web_core@0.15.0/X-ZGxpdEAzLjMuMw/es2022/src/v1_0/functions/system_functions.mjs";import{AndApi as Oe,OrApi as Ne,NotApi as Be,FormatStringApi as je,FormatNumberApi as $e,FormatCurrencyApi as Pe,FormatDateApi as Ue,PluralizeApi as Le,OpenUrlApi as _e}from"/vendor/esm/@a2ui/web_core@0.15.0/X-ZGxpdEAzLjMuMw/es2022/src/catalogs/basic/v1/functions/basic_functions_api.mjs";import{createAndImplementation as ze,createOrImplementation as Me,createNotImplementation as Ve,createFormatStringImplementation as qe,createFormatNumberImplementation as We,createFormatCurrencyImplementation as He,createFormatDateImplementation as Ge,createPluralizeImplementation as Ye,createOpenUrlImplementation as Je,isTruthyOrValid as w}from"/vendor/esm/@a2ui/web_core@0.15.0/X-ZGxpdEAzLjMuMw/es2022/src/common/basic_functions.mjs";var Z=ze(Oe,{truthy:w}),ee=Me(Ne,{truthy:w}),te=Ve(Be,{truthy:w}),ie=qe(je);function E(a){return We($e,a)}var Ke=E();function k(a){return He(Pe,a)}var Qe=k();function R(a){return Ge(Ue,a)}var Xe=R();function O(a){return Ye(Le,a)}var Ze=O(),oe=Je(_e);function ne(a){let c=a?.locale;return[...ke,ie,E(c),k(c),R(c),O(c),oe,Z,ee,te,Re]}var N=ne();import{RequiredApi as Dt,RegexApi as wt,LengthApi as Et,NumericApi as kt,EmailApi as Rt,FormatStringApi as Ot,FormatNumberApi as Nt,FormatCurrencyApi as Bt,FormatDateApi as jt,PluralizeApi as $t,OpenUrlApi as Pt,AndApi as Ut,OrApi as Lt,NotApi as _t,BASIC_FUNCTION_APIS as zt,V10_SPEC_FUNCTION_APIS as Mt}from"/vendor/esm/@a2ui/web_core@0.15.0/X-ZGxpdEAzLjMuMw/es2022/src/catalogs/basic/v1/functions/basic_functions_api.mjs";import{Catalog as et}from"/vendor/esm/@a2ui/web_core@0.15.0/X-ZGxpdEAzLjMuMw/es2022/src/catalog/types.mjs";import{BasicCatalogThemeSchema as tt}from"/vendor/esm/@a2ui/web_core@0.15.0/X-ZGxpdEAzLjMuMw/es2022/src/universal/basic_catalog/theme.mjs";var it=new et("https://a2ui.org/specification/v1_0/catalogs/basic/catalog.json","1.0",[K,q,V,X,j,G,_,W,P,J,H,M,$,Q,U,L,Y,z],N,{themeSchema:tt,...B});import{BasicCatalogThemeSchema as Wt,BasicCatalogThemeSchema as Ht,isValidCssColor as Gt}from"/vendor/esm/@a2ui/web_core@0.15.0/X-ZGxpdEAzLjMuMw/es2022/src/universal/basic_catalog/theme.mjs";import{injectBasicCatalogStyles as Jt,computeColorVariant as Kt}from"/vendor/esm/@a2ui/web_core@0.15.0/X-ZGxpdEAzLjMuMw/es2022/src/universal/basic_catalog/styles/default.mjs";import{Context as Xt}from"/vendor/esm/@a2ui/web_core@0.15.0/X-ZGxpdEAzLjMuMw/es2022/src/universal/basic_catalog/context/context.mjs";import{markdown as ei,setMarkdownRenderer as ti,getMarkdownRenderer as ii}from"/vendor/esm/@a2ui/web_core@0.15.0/X-ZGxpdEAzLjMuMw/es2022/src/universal/basic_catalog/directives/directives.mjs";export{j as A2uiAudioPlayer,$ as A2uiButton,P as A2uiCard,U as A2uiCheckBox,L as A2uiChoicePicker,_ as A2uiColumn,z as A2uiDateTimeInput,M as A2uiDivider,V as A2uiIcon,q as A2uiImage,W as A2uiList,H as A2uiModal,G as A2uiRow,Y as A2uiSlider,J as A2uiTabs,K as A2uiText,Q as A2uiTextField,X as A2uiVideo,Ut as AndApi,Z as AndImplementation,h as AudioPlayerApi,pe as BASIC_COMPONENTS,N as BASIC_FUNCTIONS,zt as BASIC_FUNCTION_APIS,Wt as BasicCatalogThemeSchema,C as ButtonApi,A as CardApi,T as CheckBoxApi,F as ChoicePickerApi,f as ColumnApi,Xt as Context,v as DateTimeInputApi,y as DividerApi,Rt as EmailApi,Bt as FormatCurrencyApi,Qe as FormatCurrencyImplementation,jt as FormatDateApi,Xe as FormatDateImplementation,Nt as FormatNumberApi,Ke as FormatNumberImplementation,Ot as FormatStringApi,ie as FormatStringImplementation,p as IconApi,m as ImageApi,Et as LengthApi,b as ListApi,x as ModalApi,_t as NotApi,te as NotImplementation,kt as NumericApi,Pt as OpenUrlApi,oe as OpenUrlImplementation,Lt as OrApi,ee as OrImplementation,$t as PluralizeApi,Ze as PluralizeImplementation,wt as RegexApi,Dt as RequiredApi,u as RowApi,S as SliderApi,g as TabsApi,l as TextApi,I as TextFieldApi,Ht as ThemeSchema,Mt as V10_SPEC_FUNCTION_APIS,d as VideoApi,o as WeightSchema,it as basicCatalog,Kt as computeColorVariant,ne as createBasicCatalogFunctions,k as createFormatCurrencyImplementation,R as createFormatDateImplementation,E as createFormatNumberImplementation,O as createPluralizeImplementation,ii as getMarkdownRenderer,Jt as injectBasicCatalogStyles,Gt as isValidCssColor,ei as markdown,ti as setMarkdownRenderer};
//# sourceMappingURL=v1.mjs.map