// Stylized-realistic water for URP.
// Gerstner vertex waves, procedural ripple normals, depth-based color,
// refraction (Opaque Texture), shoreline + crest foam, Fresnel reflections.
// Requires "Depth Texture" and "Opaque Texture" enabled on the URP asset.
Shader "Custom/Water"
{
    Properties
    {
        [Header(Color)]
        _ShallowColor ("Shallow Color", Color) = (0.15, 0.7, 0.75, 0.35)
        _DeepColor ("Deep Color", Color) = (0.02, 0.12, 0.25, 0.95)
        _DepthMaxDistance ("Depth Max Distance", Float) = 4

        // Each wave: xy = direction, z = steepness (keep the sum below 1), w = wavelength
        [Header(Waves)]
        _WaveA ("Wave A", Vector) = (1, 0, 0.22, 14)
        _WaveB ("Wave B", Vector) = (0.3, 1, 0.18, 8)
        _WaveC ("Wave C", Vector) = (-0.6, 0.8, 0.12, 4.5)
        _WaveSpeed ("Wave Speed", Float) = 1

        [Header(Surface)]
        _RippleScale ("Ripple Scale", Float) = 0.8
        _RippleStrength ("Ripple Strength", Range(0, 2)) = 0.35
        _RippleSpeed ("Ripple Speed", Float) = 0.35
        _Smoothness ("Smoothness", Range(0, 1)) = 0.9
        _SpecularIntensity ("Specular Intensity", Range(0, 4)) = 1.5
        _FresnelPower ("Fresnel Power", Range(0.5, 10)) = 5
        _ReflectionStrength ("Reflection Strength", Range(0, 1)) = 0.8
        _RefractionStrength ("Refraction Strength", Range(0, 0.2)) = 0.03

        [Header(Foam)]
        _FoamColor ("Foam Color", Color) = (1, 1, 1, 0.9)
        _FoamDistance ("Shore Foam Distance", Float) = 0.7
        _FoamNoiseScale ("Foam Noise Scale", Float) = 2.5
        _CrestFoam ("Wave Crest Foam", Range(0, 1)) = 0.3
    }

    SubShader
    {
        Tags
        {
            "RenderPipeline" = "UniversalPipeline"
            "RenderType" = "Transparent"
            "Queue" = "Transparent"
            "IgnoreProjector" = "True"
        }

        Pass
        {
            Name "WaterForward"
            Tags { "LightMode" = "UniversalForward" }

            // The shader composites the refracted scene color itself, so no blending is needed.
            Blend Off
            ZWrite Off
            Cull Back

            HLSLPROGRAM
            #pragma target 3.0
            #pragma vertex Vert
            #pragma fragment Frag

            #pragma multi_compile _ _MAIN_LIGHT_SHADOWS _MAIN_LIGHT_SHADOWS_CASCADE
            #pragma multi_compile_fragment _ _SHADOWS_SOFT _SHADOWS_SOFT_LOW _SHADOWS_SOFT_MEDIUM _SHADOWS_SOFT_HIGH
            #pragma multi_compile_fog

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/DeclareDepthTexture.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/DeclareOpaqueTexture.hlsl"

            CBUFFER_START(UnityPerMaterial)
                half4 _ShallowColor;
                half4 _DeepColor;
                float _DepthMaxDistance;
                float4 _WaveA;
                float4 _WaveB;
                float4 _WaveC;
                float _WaveSpeed;
                float _RippleScale;
                half _RippleStrength;
                float _RippleSpeed;
                half _Smoothness;
                half _SpecularIntensity;
                half _FresnelPower;
                half _ReflectionStrength;
                half _RefractionStrength;
                half4 _FoamColor;
                float _FoamDistance;
                float _FoamNoiseScale;
                half _CrestFoam;
            CBUFFER_END

            struct Attributes
            {
                float4 positionOS : POSITION;
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float3 positionWS : TEXCOORD0;
                float3 normalWS   : TEXCOORD1;
                float  viewDepth  : TEXCOORD2;
                float  crest      : TEXCOORD3; // 0 = trough, 1 = crest
                float  fogFactor  : TEXCOORD4;
            };

            // ---------- Noise ----------
            float Hash(float2 p)
            {
                p = frac(p * float2(123.34, 456.21));
                p += dot(p, p + 45.32);
                return frac(p.x * p.y);
            }

            float ValueNoise(float2 p)
            {
                float2 i = floor(p);
                float2 f = frac(p);
                float2 u = f * f * (3.0 - 2.0 * f);
                return lerp(lerp(Hash(i), Hash(i + float2(1, 0)), u.x),
                            lerp(Hash(i + float2(0, 1)), Hash(i + float2(1, 1)), u.x), u.y);
            }

            float2 NoiseSlope(float2 p)
            {
                const float e = 0.05;
                float h = ValueNoise(p);
                return float2(ValueNoise(p + float2(e, 0)) - h, ValueNoise(p + float2(0, e)) - h) / e;
            }

            // ---------- Gerstner waves ----------
            float3 GerstnerWave(float4 wave, float3 p, inout float3 tangent, inout float3 binormal, inout float amplitude)
            {
                float steepness = wave.z;
                float k = TWO_PI / max(wave.w, 0.01);
                float c = sqrt(9.8 / k) * _WaveSpeed;
                float2 d = normalize(wave.xy + 1e-5);
                float f = k * (dot(d, p.xz) - c * _Time.y);
                float a = steepness / k;
                float s = sin(f);
                float co = cos(f);

                tangent  += float3(-d.x * d.x * steepness * s, d.x * steepness * co, -d.x * d.y * steepness * s);
                binormal += float3(-d.x * d.y * steepness * s, d.y * steepness * co, -d.y * d.y * steepness * s);
                amplitude += a;
                return float3(d.x * a * co, a * s, d.y * a * co);
            }

            Varyings Vert(Attributes input)
            {
                Varyings output;

                float3 positionWS = TransformObjectToWorld(input.positionOS.xyz);
                float3 tangent = float3(1, 0, 0);
                float3 binormal = float3(0, 0, 1);
                float amplitude = 0;

                float3 offset = GerstnerWave(_WaveA, positionWS, tangent, binormal, amplitude)
                              + GerstnerWave(_WaveB, positionWS, tangent, binormal, amplitude)
                              + GerstnerWave(_WaveC, positionWS, tangent, binormal, amplitude);
                positionWS += offset;

                output.positionWS = positionWS;
                output.normalWS = normalize(cross(binormal, tangent));
                output.positionCS = TransformWorldToHClip(positionWS);
                output.viewDepth = -TransformWorldToView(positionWS).z;
                output.crest = saturate(offset.y / max(amplitude, 1e-4) * 0.5 + 0.5);
                output.fogFactor = ComputeFogFactor(output.positionCS.z);
                return output;
            }

            half4 Frag(Varyings input) : SV_Target
            {
                float3 positionWS = input.positionWS;

                // Ripple normals: two scrolling noise layers on top of the wave normal.
                float t = _Time.y * _RippleSpeed;
                float2 slope = NoiseSlope(positionWS.xz * _RippleScale + t * float2(1.0, 0.6))
                             + NoiseSlope(positionWS.xz * _RippleScale * 1.7 + t * float2(-0.7, 1.0)) * 0.6;
                float3 N = normalize(normalize(input.normalWS) + float3(-slope.x, 0, -slope.y) * _RippleStrength * 0.25);
                float3 V = GetWorldSpaceNormalizeViewDir(positionWS);

                // Depth of the water column behind this pixel.
                float2 screenUV = GetNormalizedScreenSpaceUV(input.positionCS);
                float surfaceDepth = input.viewDepth;
                float depthDiff = LinearEyeDepth(SampleSceneDepth(screenUV), _ZBufferParams) - surfaceDepth;

                // Refraction: offset by the normal, but never sample objects in front of the water.
                float2 refrUV = screenUV + N.xz * _RefractionStrength * saturate(depthDiff);
                float refrDepthDiff = LinearEyeDepth(SampleSceneDepth(refrUV), _ZBufferParams) - surfaceDepth;
                if (refrDepthDiff < 0)
                {
                    refrUV = screenUV;
                    refrDepthDiff = depthDiff;
                }
                half3 sceneColor = SampleSceneColor(refrUV);

                // Lighting
                Light light = GetMainLight(TransformWorldToShadowCoord(positionWS));
                half3 lightColor = light.color * light.shadowAttenuation;
                half NdotL = saturate(dot(N, light.direction));
                half3 ambient = SampleSH(N);

                // Water body: tint the refracted scene by depth.
                half4 waterColor = lerp(_ShallowColor, _DeepColor, saturate(refrDepthDiff / max(_DepthMaxDistance, 1e-3)));
                half3 bodyLit = waterColor.rgb * (lightColor * (0.4 + 0.6 * NdotL) + ambient);
                half3 color = lerp(sceneColor, bodyLit, waterColor.a);

                // Reflections
                half fresnel = pow(1.0 - saturate(dot(N, V)), _FresnelPower);
                half3 reflection = GlossyEnvironmentReflection(reflect(-V, N), 1.0 - _Smoothness, 1.0);
                color = lerp(color, reflection, fresnel * _ReflectionStrength);

                // Specular highlight (Blinn-Phong)
                float3 H = normalize(light.direction + V);
                half specPower = exp2(_Smoothness * 10.0 + 1.0);
                color += lightColor * pow(saturate(dot(N, H)), specPower) * _SpecularIntensity;

                // Foam: noisy shoreline band + optional wave crests.
                float foamNoise = ValueNoise(positionWS.xz * _FoamNoiseScale + _Time.y * 0.25);
                float shore = 1.0 - saturate(depthDiff / max(_FoamDistance, 1e-3));
                float shoreFoam = smoothstep(foamNoise - 0.05, foamNoise + 0.05, shore);
                float crestFoam = smoothstep(1.0 - _CrestFoam * 0.5, 1.0, input.crest) * step(0.001, _CrestFoam)
                                * smoothstep(0.3, 0.7, foamNoise);
                float foam = saturate(shoreFoam + crestFoam) * _FoamColor.a;
                color = lerp(color, _FoamColor.rgb * (lightColor * (0.5 + 0.5 * NdotL) + ambient), foam);

                color = MixFog(color, input.fogFactor);
                return half4(color, 1);
            }
            ENDHLSL
        }
    }

    FallBack Off
}
