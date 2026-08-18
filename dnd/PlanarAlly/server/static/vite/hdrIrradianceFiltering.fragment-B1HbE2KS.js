import{n as e}from"./rolldown-runtime-hePW80VL.js";import{t}from"./shaderStore-D-XQlhUT.js";import"./sceneFragmentDeclaration-DE5gko30.js";import"./hdrFilteringFunctions-DPR-QGQi.js";import"./pbrBRDFFunctions-9YzmZNQz.js";var n=e({hdrIrradianceFilteringPixelShader:()=>a}),r=`hdrIrradianceFilteringPixelShader`,i=`#include<helperFunctions>
#include<importanceSampling>
#include<pbrBRDFFunctions>
#include<hdrFilteringFunctions>
uniform samplerCube inputTexture;
#ifdef IBL_CDF_FILTERING
uniform sampler2D icdfTexture;
#endif
uniform vec2 vFilteringInfo;uniform float hdrScale;varying vec3 direction;void main() {vec3 color=irradiance(inputTexture,direction,vFilteringInfo,0.0,vec3(1.0),direction
#ifdef IBL_CDF_FILTERING
,icdfTexture
#endif
);gl_FragColor=vec4(color*hdrScale,1.0);}`;t.ShadersStore[r]||(t.ShadersStore[r]=i);var a={name:r,shader:i};export{n as t};