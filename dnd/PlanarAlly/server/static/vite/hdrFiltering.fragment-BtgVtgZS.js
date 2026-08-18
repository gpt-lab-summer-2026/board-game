import{n as e}from"./rolldown-runtime-hePW80VL.js";import{t}from"./shaderStore-D-XQlhUT.js";import"./helperFunctions-GfZ_dHKg.js";import"./hdrFilteringFunctions-B1sUzAui.js";import"./pbrBRDFFunctions-D4RobuUC.js";var n=e({hdrFilteringPixelShaderWGSL:()=>a}),r=`hdrFilteringPixelShader`,i=`#include<helperFunctions>
#include<importanceSampling>
#include<pbrBRDFFunctions>
#include<hdrFilteringFunctions>
uniform alphaG: f32;var inputTextureSampler: sampler;var inputTexture: texture_cube<f32>;uniform vFilteringInfo: vec2f;uniform hdrScale: f32;varying direction: vec3f;@fragment
fn main(input: FragmentInputs)->FragmentOutputs {var color: vec3f=radiance(uniforms.alphaG,inputTexture,inputTextureSampler,input.direction,uniforms.vFilteringInfo);fragmentOutputs.color= vec4f(color*uniforms.hdrScale,1.0);}`;t.ShadersStoreWGSL[r]||(t.ShadersStoreWGSL[r]=i);var a={name:r,shader:i};export{n as t};