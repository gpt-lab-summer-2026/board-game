import{n as e}from"./rolldown-runtime-hePW80VL.js";import{t}from"./shaderStore-D-XQlhUT.js";import"./sceneFragmentDeclaration-D8v3rwv1.js";var n=e({rgbdEncodePixelShader:()=>a}),r=`rgbdEncodePixelShader`,i=`varying vec2 vUV;uniform sampler2D textureSampler;
#include<helperFunctions>
#define CUSTOM_FRAGMENT_DEFINITIONS
void main(void) 
{gl_FragColor=toRGBD(texture2D(textureSampler,vUV).rgb);}`;t.ShadersStore[r]||(t.ShadersStore[r]=i);var a={name:r,shader:i};export{n as t};