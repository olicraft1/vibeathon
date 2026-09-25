#!/usr/bin/env python3
"""Generate the bundled sample cue files (canned-engine fallback captions).

Timings are proportional to sentence length over the real audio duration.
Run once: python3 scripts/make_sample_cues.py
"""
import json
from pathlib import Path

SAMPLES = Path(__file__).resolve().parent.parent / "samples"

TALK_EN = [
    ("Welcome everyone, and thank you for joining this session at Nerdearla.", "Bienvenidos y gracias por acompañarnos en esta sesión de Nerdearla."),
    ("My name is Alex, and today we are going to talk about scaling open source communities.", "Mi nombre es Alex, y hoy vamos a hablar de cómo escalar comunidades de open source."),
    ("Three years ago our project had five contributors and a single deploy script.", "Hace tres años nuestro proyecto tenía cinco colaboradores y un único script de deploy."),
    ("Today we have more than two thousand contributors, and we ship to production forty times a day.", "Hoy tenemos más de dos mil colaboradores y llevamos a producción cuarenta veces al día."),
    ("How did we get here?", "¿Cómo llegamos hasta acá?"),
    ("First, we invested in Kubernetes operators to automate our infrastructure.", "Primero, invertimos en operadores de Kubernetes para automatizar nuestra infraestructura."),
    ("Second, we built continuous delivery pipelines with GitHub Actions, so every pull request gets tested automatically.", "Segundo, construimos pipelines de entrega continua con GitHub Actions, así cada pull request se prueba automáticamente."),
    ("And third, we added observability with Prometheus and Grafana, which let us catch regressions before our users did.", "Y tercero, agregamos observabilidad con Prometheus y Grafana, que nos permitió detectar regresiones antes que nuestros usuarios."),
    ("The secret is not the tools, though.", "El secreto no son las herramientas, sin embargo."),
    ("The secret is boring, reliable processes and excellent documentation.", "El secreto son procesos aburridos y confiables, y documentación excelente."),
    ("If a new contributor cannot run the project in ten minutes, you have already lost them.", "Si una persona nueva no puede levantar el proyecto en diez minutos, ya la perdiste."),
    ("So write a great README, label good first issues, and be kind in code review.", "Así que escribí un gran README, etiquetá buenas primeras issues, y sé amable en el code review."),
    ("That is how open source scales: with people, patience, and a little bit of YAML.", "Así escala el open source: con personas, paciencia, y un poquito de YAML."),
    ("Thank you!", "¡Gracias!"),
]

TALK_EN2 = [
    ("Hi everyone! In this short talk we will see why Postgres is still the best default database for most applications.", "¡Hola a todos! En esta charla corta vamos a ver por qué Postgres sigue siendo la mejor base de datos por defecto para la mayoría de las aplicaciones."),
    ("People keep telling me they need a specialized datastore for every new feature: a time series database, a search engine, a graph database.", "La gente me dice que necesita un almacén de datos especializado para cada función nueva: una base de datos de series de tiempo, un motor de búsqueda, una base de datos de grafos."),
    ("But modern Postgres gives you all of that: JSON documents, full text search, and powerful indexes.", "Pero el Postgres moderno te da todo eso: documentos JSON, búsqueda de texto completo e índices potentes."),
    ("Start simple, measure your latency, and only add complexity when you can prove you need it.", "Empezá simple, medí tu latencia, y solo agregá complejidad cuando puedas demostrar que la necesitás."),
    ("Your future team will thank you.", "Tu equipo del futuro te lo va a agradecer."),
]

TALK_ES = [
    ("Bienvenidos y bienvenidas a esta charla de Nerdearla.", "Welcome to this talk at Nerdearla."),
    ("Mi nombre es Marta y hoy vamos a hablar de accesibilidad en conferencias de tecnología.", "My name is Marta and today we are going to talk about accessibility at technology conferences."),
    ("Empecemos con un dato duro: más de cuatrocientos millones de personas hablan español en el mundo, y sin embargo la mayoría de las charlas técnicas se dictan en inglés.", "Let's start with a hard fact: more than four hundred million people speak Spanish in the world, and yet most technical talks are given in English."),
    ("La barrera idiomática es real, y en cada evento vemos gente que se pierde contenido valioso por no entenderlo.", "The language barrier is real, and at every event we see people miss valuable content because they don't understand it."),
    ("Por eso construimos un sistema de subtítulos en vivo: toma el audio del escenario, lo transcribe en el idioma original y lo traduce al español en tiempo real.", "That's why we built a live captioning system: it takes the stage audio, transcribes it in the original language and translates it into Spanish in real time."),
    ("Usamos modelos abiertos como Whisper y servicios como Gemini para lograr una latencia baja, de menos de dos segundos.", "We use open models like Whisper and services like Gemini to achieve low latency, under two seconds."),
    ("Lo más importante es que sea software libre, para que cualquier conferencia del mundo pueda desplegarlo: Nerdearla, PyCon, DevFest o el meetup de tu barrio.", "The most important thing is that it is free software, so any conference in the world can deploy it: Nerdearla, PyCon, DevFest or your neighborhood meetup."),
    ("Si te interesa sumarte, todo el código está en GitHub con licencia MIT.", "If you'd like to join, all the code is on GitHub under the MIT license."),
    ("¡Muchas gracias y que disfruten el evento!", "Thank you very much and enjoy the event!"),
]


def build(pairs, duration, src_lang, other_lang):
    total = sum((len(a) + len(b)) / 2 for a, b in pairs)
    span = duration - 0.7
    t, out = 0.35, []
    for src, tr in pairs:
        dur = max(1.4, span * ((len(src) + len(tr)) / 2) / total)
        t1 = min(duration - 0.3, t + dur)
        out.append({
            "t0": round(t, 2),
            "t1": round(t1, 2),
            "texts": {src_lang: src, other_lang: tr},
        })
        t = t1
    return {
        "lang": src_lang,
        "duration": duration,
        "note": "Pre-authored captions for the bundled TTS sample (canned engine fallback).",
        "cues": out,
    }


def main():
    files = {
        "talk_en.mp3.cues.json": build(TALK_EN, 83.8, "en", "es"),
        "talk_en2.mp3.cues.json": build(TALK_EN2, 41.8, "en", "es"),
        "talk_es.mp3.cues.json": build(TALK_ES, 64.6, "es", "en"),
    }
    for name, data in files.items():
        path = SAMPLES / name
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{path}: {len(data['cues'])} cues, ends at {data['cues'][-1]['t1']}s")


if __name__ == "__main__":
    main()
