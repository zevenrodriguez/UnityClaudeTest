// Two-sided mangrove leaves (and leaf litter / debris) for URP.
// Color comes from the Blender vertex colors; adds back-lit translucency so leaves glow
// when you look up through the canopy toward the sun.
Shader "Mangrove/Foliage"
{
    Properties
    {
        _Tint ("Tint", Color) = (1, 1, 1, 1)
        _Smoothness ("Smoothness", Range(0, 1)) = 0.5
        _Translucency ("Translucency", Range(0, 2)) = 0.6
        _TranslucencyColor ("Translucency Color", Color) = (0.75, 0.85, 0.3, 1)
    }

    SubShader
    {
        Tags { "RenderPipeline" = "UniversalPipeline" "RenderType" = "Opaque" "Queue" = "Geometry" }

        HLSLINCLUDE
        #include "MangroveCommon.hlsl"

        CBUFFER_START(UnityPerMaterial)
            half4 _Tint;
            half _Smoothness;
            half _Translucency;
            half4 _TranslucencyColor;
        CBUFFER_END
        ENDHLSL

        Pass
        {
            Name "ForwardLit"
            Tags { "LightMode" = "UniversalForward" }
            Cull Off

            HLSLPROGRAM
            #pragma target 3.5
            #pragma vertex Vert
            #pragma fragment Frag
            #pragma multi_compile _ _MAIN_LIGHT_SHADOWS _MAIN_LIGHT_SHADOWS_CASCADE _MAIN_LIGHT_SHADOWS_SCREEN
            #pragma multi_compile_fragment _ _SHADOWS_SOFT _SHADOWS_SOFT_LOW _SHADOWS_SOFT_MEDIUM _SHADOWS_SOFT_HIGH
            #pragma multi_compile_fog
            #pragma multi_compile_instancing

            struct Attributes
            {
                float4 positionOS : POSITION;
                float3 normalOS   : NORMAL;
                half4  color      : COLOR;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float3 positionWS : TEXCOORD0;
                float3 normalWS   : TEXCOORD1;
                half3  color      : TEXCOORD2;
                half   fogFactor  : TEXCOORD3;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            Varyings Vert(Attributes input)
            {
                Varyings output = (Varyings)0;
                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_TRANSFER_INSTANCE_ID(input, output);
                output.positionWS = TransformObjectToWorld(input.positionOS.xyz);
                output.positionCS = TransformWorldToHClip(output.positionWS);
                output.normalWS = TransformObjectToWorldNormal(input.normalOS);
                output.color = MgToLinear(input.color.rgb);
                output.fogFactor = ComputeFogFactor(output.positionCS.z);
                return output;
            }

            half4 Frag(Varyings input, bool isFrontFace : SV_IsFrontFace) : SV_Target
            {
                UNITY_SETUP_INSTANCE_ID(input);
                half3 albedo = input.color * _Tint.rgb;
                float3 N = normalize(input.normalWS) * (isFrontFace ? 1 : -1);
                half3 color = MgLightPBR(input.positionWS, N, albedo, _Smoothness, input.positionCS, input.fogFactor);

                // light passing through the leaf from behind
                Light light = GetMainLight(TransformWorldToShadowCoord(input.positionWS));
                float3 V = GetWorldSpaceNormalizeViewDir(input.positionWS);
                half back = saturate(dot(-N, light.direction)) * (0.5 + 0.5 * pow(saturate(dot(-V, light.direction)), 4));
                color += albedo * _TranslucencyColor.rgb * light.color * light.shadowAttenuation * back * _Translucency;
                return half4(color, 1);
            }
            ENDHLSL
        }

        Pass
        {
            Name "ShadowCaster"
            Tags { "LightMode" = "ShadowCaster" }
            ZWrite On
            ZTest LEqual
            ColorMask 0
            Cull Off

            HLSLPROGRAM
            #pragma vertex MgShadowVert
            #pragma fragment MgNullFrag
            #pragma multi_compile_vertex _ _CASTING_PUNCTUAL_LIGHT_SHADOW
            #pragma multi_compile_instancing
            ENDHLSL
        }

        Pass
        {
            Name "DepthOnly"
            Tags { "LightMode" = "DepthOnly" }
            ZWrite On
            ColorMask R
            Cull Off

            HLSLPROGRAM
            #pragma vertex MgDepthVert
            #pragma fragment MgNullFrag
            #pragma multi_compile_instancing
            ENDHLSL
        }
    }

    FallBack Off
}
