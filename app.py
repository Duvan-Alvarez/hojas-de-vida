import streamlit as st
import os
import requests
from bs4 import BeautifulSoup
from analizador_cv import ResumeAnalyzer
import plotly.express as px

# Inicializar analizador
analyzer = ResumeAnalyzer()

st.set_page_config(
    page_title="Analizador de Hojas de Vida",
    page_icon="📄",
    layout="wide"
)

st.title("📄 Analizador de Hojas de Vida con IA")
st.markdown("Sube CVs en PDF o Word → análisis automático con Gemini")

tab1, tab2, tab3 = st.tabs(["📤 Subir CVs", "🔍 Ver Candidatos Procesados", "🔎 Buscar por Vacante"])

with tab1:
    st.subheader("Subir currículums")

    uploaded_files = st.file_uploader(
        "Selecciona uno o varios archivos (PDF o DOCX)",
        type=["pdf", "docx"],
        accept_multiple_files=True
    )

    if uploaded_files:
        progress = st.progress(0)
        status = st.container()

        processed = []

        for idx, file in enumerate(uploaded_files):
            try:
                temp_path = f"temp_{file.name}"
                with open(temp_path, "wb") as f:
                    f.write(file.getbuffer())

                status.info(f"Procesando {file.name}...")
                result = analyzer.process_resume(temp_path)

                if "error" in result:
                    status.error(f"Error en {file.name}: {result['error']}")
                else:
                    # Check for job matches
                    matches = []
                    if 'vacancies' in st.session_state:
                        for job in st.session_state['vacancies']:
                            match_result = analyzer.match_cv_to_job(result, job['title'], job['description'])
                            if match_result.get('match', False):
                                matches.append({
                                    'job': job,
                                    'score': match_result.get('score', 0),
                                    'reasoning': match_result.get('reasoning', ''),
                                    'matched_terms': match_result.get('matched_terms', []),
                                    'strengths': match_result.get('strengths', []),
                                    'gaps': match_result.get('gaps', [])
                                })

                    processed.append({
                        "filename": file.name,
                        "data": result,
                        "matches": matches
                    })
                    status.success(f"✓ {file.name} procesado correctamente")

                os.remove(temp_path)

            except Exception as e:
                status.error(f"Error grave en {file.name}: {str(e)}")

            progress.progress((idx + 1) / len(uploaded_files))

        if processed:
            st.markdown("### Resultados de los CVs subidos")

            for item in processed:
                data = item["data"]
                fname = item["filename"]

                with st.expander(f"📄 {fname} — {data.get('name', 'Nombre no detectado')}"):
                    col1, col2 = st.columns([1, 3])

                    with col1:
                        st.markdown("**Nombre**")
                        st.write(data.get("name", "—"))

                        st.markdown("**Contacto**")
                        st.write(data.get("contact", "—"))

                    with col2:
                        st.markdown("**Estudios**")
                        education = data.get("education", "")
                        if education:
                            st.write(education)
                        else:
                            st.write("No se detectaron estudios")

                        st.markdown("**Experiencia laboral**")
                        experience = data.get("experience", "")
                        if experience:
                            st.write(experience)
                        else:
                            st.write("No se detectó experiencia")

                        st.markdown("**Habilidades**")
                        skills = data.get("skills", "")
                        if skills:
                            st.write(skills)
                        else:
                            st.write("No se detectaron habilidades")

                        st.markdown("**Idiomas**")
                        languages = data.get("languages", "")
                        if languages:
                            st.write(languages)
                        else:
                            st.write("No se detectaron idiomas")

                        st.markdown("**Certificaciones**")
                        certifications = data.get("certifications", "")
                        if certifications:
                            st.write(certifications)
                        else:
                            st.write("No se detectaron certificaciones")

                        st.markdown("**Resumen del perfil**")
                        summary = data.get("summary", "")
                        if summary:
                            st.write(summary)
                        else:
                            st.write("No se detectó resumen")

                        # Show job matches
                        matches = item.get("matches", [])
                        if matches:
                            st.markdown("**🎯 Vacantes compatibles:**")
                            for match in matches:
                                with st.expander(f"💼 {match['job']['title']} - Score: {match['score']}%"):
                                    st.markdown(f"**Área:** {match['job']['area']}")
                                    st.markdown(f"**Descripción:** {match['job']['description']}")
                                    st.markdown(f"**Análisis de compatibilidad:** {match['reasoning']}")

                                    matched_terms = match.get('matched_terms', [])
                                    if matched_terms:
                                        st.markdown("**Términos coincidentes:**")
                                        st.write(', '.join(matched_terms))
                                    
                                    if match.get('strengths'):
                                        st.markdown("**Fortalezas:**")
                                        for strength in match['strengths']:
                                            st.markdown(f"- ✅ {strength}")
                                    
                                    if match.get('gaps'):
                                        st.markdown("**Áreas de mejora:**")
                                        for gap in match['gaps']:
                                            st.markdown(f"- ⚠️ {gap}")
                        else:
                            st.info("No se encontraron vacantes compatibles con este perfil.")

with tab2:
    st.subheader("Candidatos procesados (de la base de datos)")

    candidates = analyzer.get_all_candidates()

    if not candidates:
        st.info("Aún no hay candidatos procesados.")
    else:
        for cand in candidates:
            with st.expander(f"ID {cand['id']} — {cand['name']}"):
                st.markdown(f"**Contacto:** {cand['contact']}")

                st.markdown("**Estudios**")
                education = cand.get("education", "")
                if education:
                    st.write(education)
                else:
                    st.write("No se detectaron estudios")

                st.markdown("**Experiencia**")
                experience = cand.get("experience", "")
                if experience:
                    st.write(experience)
                else:
                    st.write("No se detectó experiencia")

                st.markdown("**Habilidades**")
                skills = cand.get("skills", "")
                if skills:
                    st.write(skills)
                else:
                    st.write("No se detectaron habilidades")

                # Encontrar la vacante más compatible para este candidato
                best_match_for_candidate = None
                highest_score_for_candidate = -1

                vacancies = st.session_state.get('vacancies', [])
                if vacancies:
                    for job in vacancies:
                        match_result = analyzer.match_cv_to_job(cand, job['title'], job['description'])
                        current_score = match_result.get('score', 0)

                        if current_score > highest_score_for_candidate:
                            highest_score_for_candidate = current_score
                            best_match_for_candidate = {
                                'job': job,
                                'score': current_score,
                                'reasoning': match_result.get('reasoning', ''),
                                'strengths': match_result.get('strengths', []),
                                'gaps': match_result.get('gaps', []),
                                'matched_terms': match_result.get('matched_terms', [])
                            }
                
                if best_match_for_candidate:
                    st.markdown("---")
                    st.markdown(f"**🎯 Vacante más compatible:**")
                    with st.expander(f"💼 {best_match_for_candidate['job']['title']} - Score: {best_match_for_candidate['score']}%"):
                        st.markdown(f"**Área:** {best_match_for_candidate['job']['area']}")
                        st.markdown(f"**Descripción:** {best_match_for_candidate['job']['description']}")
                        st.markdown(f"**Análisis de compatibilidad:** {best_match_for_candidate['reasoning']}")
                        if best_match_for_candidate.get('strengths'):
                            st.markdown("**Fortalezas:**")
                            for strength in best_match_for_candidate['strengths']:
                                st.markdown(f"- ✅ {strength}")
                        if best_match_for_candidate.get('gaps'):
                            st.markdown("**Áreas de mejora:**")
                            for gap in best_match_for_candidate['gaps']:
                                st.markdown(f"- ⚠️ {gap}")
                        if best_match_for_candidate.get('matched_terms'):
                            st.markdown("**Términos coincidentes:**")
                            st.write(', '.join(best_match_for_candidate['matched_terms']))
                else:
                    st.info("No hay vacantes cargadas o no se encontró una vacante compatible para este candidato.")

    # En la pestaña de candidatos, muestra un gráfico de skills
    st.subheader("Gráfico de habilidades de los candidatos")
    if candidates:
        skill_counts = {}
        for cand in candidates:
            for skill in cand.get("skills", []):
                skill_counts[skill] = skill_counts.get(skill, 0) + 1
        skill_names = list(skill_counts.keys())
        skill_values = list(skill_counts.values())
        fig = px.bar(skill_names, skill_values, labels={'x': 'Habilidades', 'y': 'Cantidad de candidatos'}, title='Habilidades de los candidatos')
        st.plotly_chart(fig)
    else:
        st.info("No hay candidatos para mostrar.")

with tab3:
    st.subheader("Vacantes publicadas en SalsasAderezos")

    if st.button("Actualizar vacantes"):
        try:
            url = "https://copernico.salsasaderezos.com.co/app/desarrollohumano/formulario_empleo.php"
            response = requests.get(url)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')

            # Find job listings - they are in h5 tags with job titles
            jobs = soup.find_all('h5')
            job_list = []

            for job in jobs:
                title = job.get_text(strip=True)
                if title and not title.startswith('Haz parte') and not title.startswith('Vacantes'):
                    # Get area and full description
                    area = ""
                    description_parts = []
                    current = job
                    
                    while True:
                        next_p = current.find_next('p')
                        if not next_p:
                            break
                        
                        text = next_p.get_text(strip=True)
                        if text.startswith(' Área:'):
                            area = text.replace(' Área:', '').strip()
                        elif 'Ver detalles' in text or 'Postularse' in text or text.startswith('') or text.startswith(''):
                            break
                        else:
                            # This is part of the description
                            if text and not text.startswith('') and not text.startswith('') and not text.startswith(''):
                                description_parts.append(text)
                        
                        current = next_p
                    
                    description = ' '.join(description_parts).strip()
                    
                    job_list.append({
                        'title': title,
                        'area': area,
                        'description': description
                    })

            st.session_state['vacancies'] = job_list
            st.success(f"Se encontraron {len(job_list)} vacantes.")

        except Exception as e:
            st.error(f"Error al cargar las vacantes: {str(e)}")

    # Display current vacancies
    if 'vacancies' in st.session_state and st.session_state['vacancies']:
        st.markdown("### Vacantes disponibles:")
        for job in st.session_state['vacancies']:
            with st.expander(f"💼 {job['title']}"):
                st.markdown(f"**Área:** {job['area']}")
                st.markdown(f"**Descripción:** {job['description']}")

        candidates = analyzer.get_all_candidates()
        if candidates:
            st.markdown("### 🏆 Ranking de Candidatos por Compatibilidad")
            st.caption("Análisis de cada candidato contra todas las vacantes para encontrar su mejor opción y puntaje.")

            candidate_matches = []

            for cand in candidates:
                best_match_for_candidate = None
                highest_score = -1

                for job in st.session_state['vacancies']:
                    match = analyzer.match_cv_to_job(cand, job['title'], job['description'])
                    current_score = match.get('score', 0)

                    if current_score > highest_score:
                        highest_score = current_score
                        best_match_for_candidate = {
                            'candidate': cand,
                            'job': job,
                            'score': current_score,
                            'details': match
                        }
                
                if best_match_for_candidate:
                    candidate_matches.append(best_match_for_candidate)

            if candidate_matches:
                # Ordenar candidatos por puntaje descendente
                candidate_matches.sort(key=lambda x: x['score'], reverse=True)

                for i, result in enumerate(candidate_matches):
                    candidate_name = result['candidate'].get('name', 'Nombre no disponible')
                    job_title = result['job']['title']
                    score = result['score']
                    
                    # Usar st.success para el primer lugar, st.info para los demás
                    if i == 0:
                        st.success(f"**1. {candidate_name} → {job_title} ({score}%)**")
                    else:
                        st.info(f"**{i + 1}. {candidate_name} → {job_title} ({score}%)**")

                    with st.expander("Ver detalles del análisis"):
                        st.markdown(f"**Análisis:** {result['details'].get('reasoning', 'No disponible.')}")
                        if result['details'].get('strengths'):
                            st.markdown("**Fortalezas:**")
                            for strength in result['details']['strengths']:
                                st.markdown(f"- ✅ {strength}")
                        if result['details'].get('gaps'):
                            st.markdown("**Áreas de mejora:**")
                            for gap in result['details']['gaps']:
                                st.markdown(f"- ⚠️ {gap}")
            else:
                st.warning("No se pudo determinar una mejor coincidencia. Asegúrate de tener candidatos y vacantes cargados.")
        else:
            st.info("No hay candidatos procesados en la base de datos para analizar compatibilidad.")
    else:
        st.info("No hay vacantes cargadas. Haz clic en 'Actualizar vacantes'.")

st.markdown("---")
st.caption("")