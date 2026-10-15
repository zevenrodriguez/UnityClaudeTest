// Procedural night sky for URP: gradient sky with horizon airglow, two layers of
// colored twinkling stars, a Milky Way band with dust lanes and a bright core,
// and a phased moon with craters and halo. No textures required.
// By default the moon sits where the main directional light comes from, so the
// moonlight in the scene matches the moon in the sky.
Shader "Custom/NightSky"
{
    Properties
    {
        [Header(Sky)]
        _ZenithColor ("Zenith Color", Color) = (0.003, 0.006, 0.02, 1)
        _HorizonColor ("Horizon Color", Color) = (0.02, 0.035, 0.07, 1)
        _HorizonGlowColor ("Horizon Glow", Color) = (0.035, 0.05, 0.06, 1)
        _HorizonGlowHeight ("Horizon Glow Height", Range(0.01, 1)) = 0.12
        _GroundColor ("Ground Color", Color) = (0.004, 0.005, 0.01, 1)
        _Exposure ("Exposure", Range(0, 8)) = 1

        [Header(Stars)]
        _StarDensity ("Star Density", Range(20, 400)) = 140
        _StarCoverage ("Star Coverage", Range(0, 1)) = 0.55
        _StarSize ("Star Size", Range(0.02, 0.3)) = 0.1
        _StarBrightness ("Star Brightness", Range(0, 10)) = 2
        _StarColorVariation ("Star Color Variation", Range(0, 1)) = 0.6
        _TwinkleSpeed ("Twinkle Speed", Range(0, 10)) = 2.5
        _TwinkleAmount ("Twinkle Amount", Range(0, 1)) = 0.45

        [Header(Milky Way)]
        _MilkyWayIntensity ("Intensity", Range(0, 3)) = 0.5
        _MilkyWayWidth ("Width", Range(0.02, 0.6)) = 0.16
        _MilkyWayAxis ("Galactic Pole Direction", Vector) = (0.35, 0.55, 0.75, 0)
        _MilkyWayCoreAngle ("Core Angle (deg)", Range(0, 360)) = 210
        _MilkyWayColor ("Color", Color) = (0.7, 0.78, 1, 1)
        _MilkyWayCoreColor ("Core Color", Color) = (1, 0.85, 0.65, 1)
        _DustStrength ("Dust Lanes", Range(0, 1)) = 0.8

        [Header(Moon)]
        [ToggleUI] _MoonFollowsLight ("Moon Follows Main Light", Float) = 1
        _MoonDirection ("Moon Direction (if not following light)", Vector) = (-0.4, 0.5, 0.75, 0)
        _MoonSize ("Moon Size (deg)", Range(0.3, 15)) = 3
        _MoonPhase ("Moon Phase (0 full, 1 new)", Range(0, 1)) = 0.25
        _MoonColor ("Moon Color", Color) = (1, 0.97, 0.9, 1)
        _MoonIntensity ("Moon Intensity", Range(0, 10)) = 2.5
        _MoonGlowSize ("Moon Halo Size", Range(0.01, 1)) = 0.12
        _MoonGlowIntensity ("Moon Halo Intensity", Range(0, 2)) = 0.35

        [Header(Motion)]
        _SkyRotationSpeed ("Rotation Speed (deg per sec)", Float) = 0.3
        _PoleAxis ("Celestial Pole Direction", Vector) = (0, 0.6, 0.8, 0)
    }

    SubShader
    {
        Tags
        {
            "RenderPipeline" = "UniversalPipeline"
            "Queue" = "Background"
            "RenderType" = "Background"
            "PreviewType" = "Skybox"
        }
        Cull Off
        ZWrite Off

        Pass
        {
            HLSLPROGRAM
            #pragma target 3.0
            #pragma vertex Vert
            #pragma fragment Frag

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

            CBUFFER_START(UnityPerMaterial)
                half4 _ZenithColor;
                half4 _HorizonColor;
                half4 _HorizonGlowColor;
                float _HorizonGlowHeight;
                half4 _GroundColor;
                float _Exposure;

                float _StarDensity;
                float _StarCoverage;
                float _StarSize;
                float _StarBrightness;
                float _StarColorVariation;
                float _TwinkleSpeed;
                float _TwinkleAmount;

                float _MilkyWayIntensity;
                float _MilkyWayWidth;
                float4 _MilkyWayAxis;
                float _MilkyWayCoreAngle;
                half4 _MilkyWayColor;
                half4 _MilkyWayCoreColor;
                float _DustStrength;

                float _MoonFollowsLight;
                float4 _MoonDirection;
                float _MoonSize;
                float _MoonPhase;
                half4 _MoonColor;
                float _MoonIntensity;
                float _MoonGlowSize;
                float _MoonGlowIntensity;

                float _SkyRotationSpeed;
                float4 _PoleAxis;
            CBUFFER_END

            struct Attributes
            {
                float4 positionOS : POSITION;
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float3 direction  : TEXCOORD0;
            };

            Varyings Vert(Attributes input)
            {
                Varyings output;
                output.positionCS = TransformObjectToHClip(input.positionOS.xyz);
                output.direction = input.positionOS.xyz;
                return output;
            }

            // ---------- Hashing & noise ----------
            float Hash13(float3 p)
            {
                p = frac(p * 0.1031);
                p += dot(p, p.zyx + 31.32);
                return frac((p.x + p.y) * p.z);
            }

            float3 Hash33(float3 p)
            {
                p = frac(p * float3(0.1031, 0.1030, 0.0973));
                p += dot(p, p.yxz + 33.33);
                return frac((p.xxy + p.yxx) * p.zyx);
            }

            float Noise3(float3 p)
            {
                float3 i = floor(p);
                float3 f = frac(p);
                float3 u = f * f * (3.0 - 2.0 * f);
                return lerp(
                    lerp(lerp(Hash13(i), Hash13(i + float3(1, 0, 0)), u.x),
                         lerp(Hash13(i + float3(0, 1, 0)), Hash13(i + float3(1, 1, 0)), u.x), u.y),
                    lerp(lerp(Hash13(i + float3(0, 0, 1)), Hash13(i + float3(1, 0, 1)), u.x),
                         lerp(Hash13(i + float3(0, 1, 1)), Hash13(i + float3(1, 1, 1)), u.x), u.y), u.z);
            }

            float Fbm3(float3 p, int octaves)
            {
                float sum = 0, amp = 0.5, norm = 0;
                for (int k = 0; k < octaves; k++)
                {
                    sum += amp * Noise3(p);
                    norm += amp;
                    p = p * 2.03 + 17.1;
                    amp *= 0.5;
                }
                return sum / norm;
            }

            float3 RotateAround(float3 v, float3 axis, float angle)
            {
                float s, c;
                sincos(angle, s, c);
                return v * c + cross(axis, v) * s + axis * dot(axis, v) * (1 - c);
            }

            // ---------- Stars ----------
            float3 StarColor(float t)
            {
                // Blue-white -> white -> orange, like stellar temperature.
                float3 c = lerp(float3(0.62, 0.74, 1.0), float3(1, 1, 1), saturate(t * 2));
                return lerp(c, float3(1.0, 0.74, 0.48), saturate(t * 2 - 1));
            }

            // One star per grid cell on a sphere of radius `density`. Stars whose projection
            // lands near a cell edge are dropped so none get clipped.
            float3 StarLayer(float3 dir, float density, float coverage, float seed, float pixelAngle)
            {
                float3 cell = floor(dir * density);
                float3 rnd = Hash33(cell + seed);
                float3 starPos = cell + 0.2 + 0.6 * Hash33(cell + seed + 17.0);
                float3 starDir = normalize(starPos);
                float3 local = starDir * density - cell;
                float3 inCell = step(0.15, local) * step(local, 0.85);
                float valid = step(rnd.x, coverage) * inCell.x * inCell.y * inCell.z;

                float d = length(dir - starDir);
                float size = max(_StarSize / density, pixelAngle * 0.7);
                float core = exp(-(d * d) / (size * size));

                float magnitude = pow(rnd.y, 7.0) * 6.0 + 0.12; // many faint, few bright
                float twinkle = 1 - _TwinkleAmount * (0.5 + 0.5 * sin(_Time.y * _TwinkleSpeed * (0.6 + rnd.z) + rnd.y * 80.0));
                float3 color = lerp(float3(1, 1, 1), StarColor(rnd.z), _StarColorVariation);
                return color * core * magnitude * twinkle * valid;
            }

            half4 Frag(Varyings input) : SV_Target
            {
                float3 dir = normalize(input.direction);
                float pixelAngle = length(fwidth(dir));

                float aboveHorizon = smoothstep(-0.02, 0.0, dir.y);
                float extinction = smoothstep(-0.02, 0.18, dir.y); // stars dim through thick air near the horizon

                // ---------- Sky gradient ----------
                float h = saturate(dir.y);
                float3 sky = lerp(_HorizonColor.rgb, _ZenithColor.rgb, sqrt(h));
                sky += _HorizonGlowColor.rgb * exp(-h / _HorizonGlowHeight);

                // ---------- Moon setup ----------
                float3 moonDir = _MoonFollowsLight > 0.5 ? _MainLightPosition.xyz : _MoonDirection.xyz;
                moonDir = normalize(moonDir + float3(0, 1e-5, 0));
                float phase = _MoonPhase * PI;
                float illumination = 0.5 + 0.5 * cos(phase);
                float cosMoon = dot(dir, moonDir);
                float moonAngle = acos(clamp(cosMoon, -1, 1));
                float halo = exp(-moonAngle / _MoonGlowSize) * _MoonGlowIntensity * illumination;
                sky += _MoonColor.rgb * illumination * 0.015 * pow(saturate(cosMoon * 0.5 + 0.5), 4); // moonlit sky

                // ---------- Rotating celestial sphere ----------
                float3 rdir = RotateAround(dir, normalize(_PoleAxis.xyz + 1e-5), radians(_SkyRotationSpeed) * _Time.y);

                // ---------- Milky Way ----------
                float3 n = normalize(_MilkyWayAxis.xyz + 1e-5);
                float3 t1 = normalize(cross(n, abs(n.y) < 0.99 ? float3(0, 1, 0) : float3(1, 0, 0)));
                float3 t2 = cross(n, t1);
                float coreAngle = radians(_MilkyWayCoreAngle);
                float3 coreDir = t1 * cos(coreAngle) + t2 * sin(coreAngle);
                float core = pow(saturate(dot(rdir, coreDir)), 4);

                float b = dot(rdir, n); // galactic latitude (sine)
                float width = _MilkyWayWidth * (1 + core * 1.2);
                float band = exp(-(b * b) / (width * width));
                float clouds = Fbm3(rdir * 6.0, 5);
                float fine = Fbm3(rdir * 28.0, 3);
                float dustNoise = smoothstep(0.45, 0.7, Fbm3(rdir * 10.0 + 5.0, 5));
                float laneOffset = (b - width * 0.15) / (width * 0.45);
                float dust = dustNoise * exp(-laneOffset * laneOffset);
                float milkyWay = band * (0.3 + 0.7 * clouds) * (0.7 + 0.3 * fine)
                               * (1 - _DustStrength * dust) * (0.5 + 1.5 * core);
                float3 milkyWayColor = lerp(_MilkyWayColor.rgb, _MilkyWayCoreColor.rgb, core)
                                     * milkyWay * _MilkyWayIntensity * 0.15;

                // ---------- Stars ----------
                float coverage = _StarCoverage * (1 + band * 1.5); // denser along the galactic band
                float3 stars = StarLayer(rdir, _StarDensity, coverage, 0.0, pixelAngle)
                             + StarLayer(rdir, _StarDensity * 2.1, coverage, 41.0, pixelAngle) * 0.45;
                stars *= _StarBrightness * (1 - saturate(halo * 3)); // moonlight washes out nearby stars

                float3 color = sky + (stars + milkyWayColor) * extinction;
                color += _MoonColor.rgb * halo;

                // ---------- Moon disk ----------
                float moonRadius = tan(radians(_MoonSize * 0.5));
                float3 moonRight = normalize(cross(abs(moonDir.y) > 0.99 ? float3(1, 0, 0) : float3(0, 1, 0), moonDir));
                float3 moonUp = cross(moonDir, moonRight);
                float2 uv = float2(dot(dir, moonRight), dot(dir, moonUp)) / (max(cosMoon, 1e-4) * moonRadius);
                float r2 = dot(uv, uv);
                float edge = max(fwidth(r2), 1e-4);
                float moonMask = (1 - smoothstep(1 - edge, 1 + edge, r2)) * step(0, cosMoon);

                float3 moonNormal = float3(uv, sqrt(saturate(1 - r2)));
                float3 sunOnMoon = float3(sin(phase), 0, cos(phase));
                float lit = smoothstep(-0.04, 0.08, dot(moonNormal, sunOnMoon));
                float maria = smoothstep(0.45, 0.65, Fbm3(moonNormal * 2.5 + 3.0, 4));
                float craters = Fbm3(moonNormal * 14.0, 3);
                float albedo = (0.78 - 0.32 * maria + (craters - 0.5) * 0.2) * (0.75 + 0.25 * moonNormal.z);
                float3 moon = _MoonColor.rgb * albedo * (lit * _MoonIntensity + 0.015); // + faint earthshine

                color = lerp(color, moon + sky, moonMask);

                // ---------- Below horizon ----------
                color = lerp(_GroundColor.rgb, color, aboveHorizon);

                return half4(color * _Exposure, 1);
            }
            ENDHLSL
        }
    }

    FallBack Off
}
