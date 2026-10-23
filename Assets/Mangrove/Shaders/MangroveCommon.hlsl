// Shared helpers for the mangrove shaders: noise, sRGB vertex colors, derivative bump,
// URP PBR lighting, and the ShadowCaster / DepthOnly passes.
#ifndef MANGROVE_COMMON_INCLUDED
#define MANGROVE_COMMON_INCLUDED

#include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
#include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"

// ---------- Noise ----------
float MgHash(float3 p)
{
    p = frac(p * 0.3183099 + 0.1);
    p *= 17.0;
    return frac(p.x * p.y * p.z * (p.x + p.y + p.z));
}

float MgNoise(float3 x)
{
    float3 i = floor(x);
    float3 f = frac(x);
    f = f * f * (3.0 - 2.0 * f);
    return lerp(lerp(lerp(MgHash(i), MgHash(i + float3(1, 0, 0)), f.x),
                     lerp(MgHash(i + float3(0, 1, 0)), MgHash(i + float3(1, 1, 0)), f.x), f.y),
                lerp(lerp(MgHash(i + float3(0, 0, 1)), MgHash(i + float3(1, 0, 1)), f.x),
                     lerp(MgHash(i + float3(0, 1, 1)), MgHash(i + float3(1, 1, 1)), f.x), f.y), f.z);
}

float MgFbm(float3 p, int octaves)
{
    float s = 0, a = 0.5;
    for (int i = 0; i < octaves; i++)
    {
        s += a * MgNoise(p);
        p = p * 2.03 + 17.1;
        a *= 0.5;
    }
    return s / (1.0 - pow(0.5, octaves)); // roughly 0..1
}

// Distance to the nearest random feature point, in cell units (pores, barnacles, specks).
float MgCells(float3 p)
{
    float3 i = floor(p);
    float3 f = frac(p);
    float d = 8.0;
    [unroll] for (int z = -1; z <= 1; z++)
    [unroll] for (int y = -1; y <= 1; y++)
    [unroll] for (int x = -1; x <= 1; x++)
    {
        float3 o = float3(x, y, z);
        float3 r = o + float3(MgHash(i + o), MgHash(i + o + 11.7), MgHash(i + o + 23.3)) - f;
        d = min(d, dot(r, r));
    }
    return sqrt(d);
}

// Blender exports vertex colors as sRGB; Unity passes them through untouched.
half3 MgToLinear(half3 c)
{
    return lerp(c / 12.92, pow(abs((c + 0.055) / 1.055), 2.4), step(0.04045, c));
}

// Bump from a height value (meters) using screen-space derivatives; no UVs or tangents needed.
float3 MgBumpNormal(float3 N, float3 positionWS, float height)
{
    float3 dpdx = ddx(positionWS);
    float3 dpdy = ddy(positionWS);
    float3 r1 = cross(dpdy, N);
    float3 r2 = cross(N, dpdx);
    float det = dot(dpdx, r1);
    float3 grad = sign(det) * (ddx(height) * r1 + ddy(height) * r2);
    return normalize(abs(det) * N - grad);
}

half3 MgLightPBR(float3 positionWS, float3 N, half3 albedo, half smoothness, float4 positionCS, half fogFactor)
{
    InputData inputData = (InputData)0;
    inputData.positionWS = positionWS;
    inputData.normalWS = N;
    inputData.viewDirectionWS = GetWorldSpaceNormalizeViewDir(positionWS);
    inputData.shadowCoord = TransformWorldToShadowCoord(positionWS);
    inputData.fogCoord = fogFactor;
    inputData.bakedGI = SampleSH(N);
    inputData.normalizedScreenSpaceUV = GetNormalizedScreenSpaceUV(positionCS);
    inputData.shadowMask = half4(1, 1, 1, 1);

    SurfaceData surface = (SurfaceData)0;
    surface.albedo = albedo;
    surface.smoothness = smoothness;
    surface.occlusion = 1;
    surface.alpha = 1;
    surface.normalTS = half3(0, 0, 1);

    half3 color = UniversalFragmentPBR(inputData, surface).rgb;
    return MixFog(color, fogFactor);
}

// ---------- ShadowCaster / DepthOnly ----------
float3 _LightDirection;
float3 _LightPosition;

struct MgShadowAttributes
{
    float4 positionOS : POSITION;
    float3 normalOS   : NORMAL;
    UNITY_VERTEX_INPUT_INSTANCE_ID
};

float4 MgShadowVert(MgShadowAttributes input) : SV_POSITION
{
    UNITY_SETUP_INSTANCE_ID(input);
    float3 positionWS = TransformObjectToWorld(input.positionOS.xyz);
    float3 normalWS = TransformObjectToWorldNormal(input.normalOS);
#if defined(_CASTING_PUNCTUAL_LIGHT_SHADOW)
    float3 lightDirectionWS = normalize(_LightPosition - positionWS);
#else
    float3 lightDirectionWS = _LightDirection;
#endif
    float4 positionCS = TransformWorldToHClip(ApplyShadowBias(positionWS, normalWS, lightDirectionWS));
#if UNITY_REVERSED_Z
    positionCS.z = min(positionCS.z, UNITY_NEAR_CLIP_VALUE);
#else
    positionCS.z = max(positionCS.z, UNITY_NEAR_CLIP_VALUE);
#endif
    return positionCS;
}

float4 MgDepthVert(MgShadowAttributes input) : SV_POSITION
{
    UNITY_SETUP_INSTANCE_ID(input);
    return TransformObjectToHClip(input.positionOS.xyz);
}

half4 MgNullFrag() : SV_Target
{
    return 0;
}

#endif
