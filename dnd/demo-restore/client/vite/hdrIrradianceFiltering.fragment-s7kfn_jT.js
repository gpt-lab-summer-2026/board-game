import{n as e}from"./rolldown-runtime-hePW80VL.js";import{t}from"./shaderStore-D-XQlhUT.js";import"./helperFunctions-GfZ_dHKg.js";import"./hdrFilteringFunctions-B1sUzAui.js";import"./pbrBRDFFunctions-D4RobuUC.js";var n=e({hdrIrradianceFilteringPixelShaderWGSL:()=>a}),r=`hdrIrradianceFilteringPixelShader`,i=`#include<helperFunctions>
#include<importanceSampling>
#include<pbrBRDFFunctions>
#include<hdrFilteringFunctions>
var inputTextureSampler: sampler;var inputTexture: texture_cube<f32>;
#ifdef IBL_CDF_FILTERING
var icdfTextureSampler: sampler;var icdfTexture: texture_2d<f32>;
#endif
uniform vFilteringInfo: vec2f;uniform hdrScale: f32;varying direction: vec3f;@fragment
fn main(input: FragmentInputs)->FragmentOutputs {var color: vec3f=irradiance(inputTexture,inputTextureSampler,input.direction,uniforms.vFilteringInfo,0.0,vec3f(1.0),input.direction
#ifdef IBL_CDF_FILTERING
,icdfTexture,icdfTextureSampler
#endif
);fragmentOutputs.color= vec4f(color*uniforms.hdrScale,1.0);}`;t.ShadersStoreWGSL[r]||(t.ShadersStoreWGSL[r]=i);var a={name:r,shader:i};export{n as t};