import{n as e}from"./rolldown-runtime-QTnfLwEv.js";import{t}from"./shaderStore-D-XQlhUT.js";import"./helperFunctions-BZ8n8qXg.js";var n=e({rgbdEncodePixelShaderWGSL:()=>a}),r=`rgbdEncodePixelShader`,i=`varying vUV: vec2f;var textureSamplerSampler: sampler;var textureSampler: texture_2d<f32>;
#include<helperFunctions>
#define CUSTOM_FRAGMENT_DEFINITIONS
@fragment
fn main(input: FragmentInputs)->FragmentOutputs {fragmentOutputs.color=toRGBD(textureSample(textureSampler,textureSamplerSampler,input.vUV).rgb);}`;t.ShadersStoreWGSL[r]||(t.ShadersStoreWGSL[r]=i);var a={name:r,shader:i};export{n as t};