# Analizador de Hojas de Vida en Python
# Requisitos previos: Instalar las bibliotecas necesarias
# pip install pypdf python-docx
# Nota: SpaCy no es compatible con Python 3.14, se ha removido temporalmente
import google.genai as genai
import json
import os
import logging
import requests # Used in extract_job_requirements_from_url
from bs4 import BeautifulSoup # Used in extract_job_requirements_from_url
from pypdf import PdfReader
import docx
import re
import sqlite3
from sqlite3 import Error
from typing import Dict, Optional # type: ignore

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configura tu API Key. Es recomendable cargarla desde variables de entorno por seguridad.
# Por ejemplo: os.getenv("GEMINI_API_KEY")
GEMINI_API_KEY = os.getenv("AIzaSyA9t5rCFnfnun3Ygf8EmM-K1L89oJalT-o")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
model = None
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-pro')
else:
    logger.warning("La variable de entorno GEMINI_API_KEY no está configurada. Las funciones de IA no estarán disponibles.")
# Cargar modelo de SpaCy para español (removido por incompatibilidad)
# nlp = spacy.load("es_core_news_sm")

class ResumeAnalyzer:
    def __init__(self, db_path: str = "resumes.db"):
        self.db_path = db_path
        self.conn = self.create_connection()
        self.create_table()

    def create_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn


    def create_table(self):
        """Crea la tabla para almacenar la información de los CVs."""
        if self.conn:
            try:
                cursor = self.conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS candidates (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT,
                        contact TEXT,
                        education TEXT,
                        experience TEXT,
                        skills TEXT
                    )
                ''')
                self.conn.commit()
                print("Tabla 'candidates' creada o ya existe.")
            except Error as e:
                print(e)

    def get_all_candidates(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM candidates")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def read_pdf(self, file_path: str) -> str:
        """Lee el contenido de un archivo PDF."""
        text = ""
        with open(file_path, "rb") as file:
            reader = PdfReader(file)
            for page in reader.pages:
                text += page.extract_text() + "\n"
        return text

    def read_word(self, file_path: str) -> str:
        """Lee el contenido de un archivo Word (.docx)."""
        doc = docx.Document(file_path)
        text = "\n".join([para.text for para in doc.paragraphs])
        return text
    
    

    def extract_information(self, text: str) -> Dict[str, str]:
        """Extrae información relevante usando Gemini AI con instrucciones mejoradas."""
        prompt = f"""
        Eres un asistente experto en análisis de currículums.
        Analiza el siguiente texto en español y extrae la información en un único objeto JSON válido.

        IMPORTANTE:
        - Responde ÚNICAMENTE con un objeto JSON válido, sin ningún texto adicional.
        - Si no encuentras información, usa cadena vacía "".
        - Para experiencia, incluye años, puestos, empresas y logros clave si están presentes.
        - Para habilidades, lista técnicas y blandas.
        - Para idiomas, indica idioma y nivel si aparece.
        - Para certificaciones, lista el nombre de la certificación.
        - Para el resumen, extrae el perfil ejecutivo o el objetivo profesional.

        Campos a extraer:
        - name
        - contact
        - education
        - experience
        - skills
        - languages
        - certifications
        - summary

        Ejemplo de salida esperada:
        {{
            "name": "María González Rodríguez",
            "contact": "maria.gonzalez@email.com, +57 300 123 4567, Bogotá, Colombia",
            "education": "Ingeniería Industrial, 2015-2020. Especialización en Gestión de Calidad",
            "experience": "Gerente de Producción: Lideré equipo de 15 personas. Analista de Procesos: Optimizé procesos reduciendo costos en 20%",
            "skills": "Python, SQL, Gestión de Proyectos, Liderazgo de Equipos, ISO 9001, Lean Manufacturing",
            "languages": "Español nativo, Inglés intermedio",
            "certifications": "ISO 9001 Internal Auditor, Scrum Master",
            "summary": "Profesional en ingeniería con experiencia en gestión de operaciones y mejora continua."
        }}

        Texto del CV a analizar:
        {text}
        """

        try:
            if model is None:
                logger.info("API de Gemini no disponible, usando extracción local")
                info = self._extract_with_regex(text)
                info["raw_text"] = text
                return info

            response = model.generate_content(
                contents=prompt
            )
            response_text = response.text.strip()
            logger.info(f"Respuesta de Gemini: {response_text[:200]}...")

            info = self._parse_json_response(response_text)
            info.setdefault("name", "")
            info.setdefault("contact", "")
            info.setdefault("education", "")
            info.setdefault("experience", "")
            info.setdefault("skills", "")
            info.setdefault("languages", "")
            info.setdefault("certifications", "")
            info.setdefault("summary", "")
            info["raw_text"] = text
            logger.info("JSON extraído exitosamente de Gemini")
            return info

        except Exception as e:
            logger.error(f"Error en extracción con Gemini: {e}")
            logger.info("Usando extracción básica con regex")
            info = self._extract_with_regex(text)
            info["raw_text"] = text
            return info

    def _parse_json_response(self, response_text: str) -> Dict[str, any]:
        """Intentar extraer y limpiar JSON de la respuesta del modelo."""
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if not json_match:
            raise ValueError("No se encontró JSON en la respuesta")

        payload = json_match.group(0)
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            cleaned = re.sub(r'[\r\n]+', ' ', payload)
            cleaned = re.sub(r',\s*}', '}', cleaned)
            cleaned = re.sub(r',\s*\]', ']', cleaned)
            cleaned = re.sub(r'\bNone\b', '""', cleaned)
            return json.loads(cleaned)

    def _extract_section(self, text: str, headings: list[str]) -> str:
        """Extrae el contenido de una sección basada en encabezados comunes."""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        section_lines = []
        capture = False
        stop_headings = ['experiencia', 'habilidades', 'educación', 'estudios', 'formación', 'contacto', 'idiomas', 'certificaciones', 'referencias', 'proyectos', 'perfil']

        for line in lines:
            lower_line = line.lower()
            if any(heading in lower_line for heading in headings):
                capture = True
                continue
            if capture and any(stop_heading in lower_line for stop_heading in stop_headings):
                break
            if capture:
                section_lines.append(line)

        return ' '.join(section_lines).strip()

    def _extract_with_regex(self, text: str) -> Dict[str, str]:
        """Extracción básica usando expresiones regulares."""
        cleaned_text = re.sub(r'\r\n?', '\n', text).strip()
        lines = [line.strip() for line in cleaned_text.split('\n') if line.strip()]

        info = {
            "name": "",
            "contact": "",
            "education": "",
            "experience": "",
            "skills": "",
            "languages": "",
            "certifications": "",
            "summary": "",
            "raw_text": cleaned_text
        }

        # Extraer nombre a partir de encabezados comunes o de las primeras líneas
        for line in lines[:8]:
            if re.search(r'\b(?:nombre completo|nombre)\b', line, re.I):
                candidate = re.sub(r'(?i)nombre completo?:\s*', '', line).strip()
                if candidate:
                    info["name"] = candidate
                    break

        if not info["name"]:
            for line in lines[:8]:
                if re.search(r'\bhoja de vida\b|\bcurr[ií]culum\b|\bcv\b', line, re.I):
                    continue
                if 1 < len(line.split()) <= 6 and re.match(r'^[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñü\s]+$', line):
                    info["name"] = line
                    break

        # Extraer datos de contacto
        contacts = []
        emails = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b', cleaned_text)
        phones = re.findall(r'\b(?:\+?\d{1,3}[-.\s]?)?(?:\d{3}[-.\s]?\d{3}[-.\s]?\d{4}|\d{4}[-.\s]?\d{4})\b', cleaned_text)
        linkedin = re.findall(r'https?://(?:www\.)?linkedin\.com/[A-Za-z0-9_/\-]+', cleaned_text, re.I)

        contacts.extend(emails)
        contacts.extend(phones)
        contacts.extend(linkedin)
        contacts = list(dict.fromkeys([contact.strip() for contact in contacts if contact.strip()]))
        info["contact"] = ', '.join(contacts)

        # Extraer secciones completas usando encabezados comunes
        education_section = self._extract_section(cleaned_text, ['educación', 'formación académica', 'estudios', 'colegio', 'universidad', 'bachiller'])
        experience_section = self._extract_section(cleaned_text, ['experiencia', 'historial laboral', 'antecedentes', 'experiencia profesional', 'trayectoria'])
        skills_section = self._extract_section(cleaned_text, ['habilidades', 'competencias', 'conocimientos', 'destrezas', 'técnicas', 'soft skills'])

        if education_section:
            info["education"] = education_section
        else:
            education_keywords = ['educación', 'estudios', 'universidad', 'colegio', 'bachiller', 'licenciatura', 'ingeniería', 'técnico', 'maestría', 'doctorado']
            education_lines = [line for line in lines if any(keyword in line.lower() for keyword in education_keywords)]
            info["education"] = ' '.join(education_lines[:5])

        if experience_section:
            info["experience"] = experience_section
        else:
            experience_keywords = ['experiencia', 'trabajo', 'empleo', 'puesto', 'cargo', 'empresa', 'años', 'auxiliar', 'logística', 'almacén', 'producción', 'operario', 'recepción', 'despacho', 'inventarios', 'envasado']
            experience_lines = [line for line in lines if any(keyword in line.lower() for keyword in experience_keywords)]
            info["experience"] = ' '.join(experience_lines[:10])

        skills_keywords = [
            'python', 'java', 'javascript', 'sql', 'html', 'css', 'react', 'node', 'git', 'linux', 'windows',
            'excel', 'office', 'word', 'powerpoint', 'microsoft office', 'sap', 'logística', 'almacén', 'inventarios',
            'recepción', 'despacho', 'empaquetado', 'montacargas', 'producción', 'control de calidad', 'seguridad industrial',
            'trabajo en equipo', 'comunicación', 'atención al cliente', 'gestión del tiempo', 'planificación', 'organización',
            'ingles', 'español'
        ]
        found_skills = []
        lower_text = cleaned_text.lower()
        for skill in skills_keywords:
            if re.search(rf'\b{re.escape(skill)}\b', lower_text, re.I):
                found_skills.append(skill.title())

        if skills_section:
            info["skills"] = skills_section
        elif found_skills:
            info["skills"] = ', '.join(dict.fromkeys(found_skills))
        else:
            skills_lines = [line for line in lines if any(keyword in line.lower() for keyword in skills_keywords)]
            info["skills"] = ' '.join(dict.fromkeys(skills_lines[:8]))

        summary_section = self._extract_section(cleaned_text, ['perfil', 'resumen', 'objetivo profesional', 'objetivo', 'perfil profesional', 'sobre mí', 'sobre mi'])
        languages_section = self._extract_section(cleaned_text, ['idiomas', 'lenguas'])
        certifications_section = self._extract_section(cleaned_text, ['certificaciones', 'certificaciones y cursos', 'cursos', 'diplomas'])

        if summary_section:
            info["summary"] = summary_section
        else:
            candidate_lines = [line for line in lines[:6] if not re.search(r'\b(curr[ií]culum|hoja de vida|perfil|experiencia|educación|formación|habilidades|idiomas|certificaciones)\b', line, re.I)]
            info["summary"] = ' '.join(candidate_lines[:2])

        if languages_section:
            info["languages"] = languages_section
        else:
            language_keywords = ['español', 'inglés', 'inglés avanzado', 'inglés intermedio', 'inglés básico', 'alemán', 'francés', 'portugués']
            language_lines = [line for line in lines if any(keyword in line.lower() for keyword in language_keywords)]
            info["languages"] = ' '.join(dict.fromkeys(language_lines[:5]))

        if certifications_section:
            info["certifications"] = certifications_section
        else:
            cert_keywords = ['certificación', 'certificado', 'curso', 'diploma', 'certificado en', 'certificado de']
            cert_lines = [line for line in lines if any(keyword in line.lower() for keyword in cert_keywords)]
            info["certifications"] = ' '.join(dict.fromkeys(cert_lines[:5]))

        logger.info(f"Extracción con regex completada: {info}")
        return info

    def _normalize_text(self, text: str) -> list:
        return re.findall(r'\b[\wáéíóúñüÁÉÍÓÚÑÜ]+\b', text.lower())

    def _score_candidate_against_requirements(self, requirements: str, candidate_text: str) -> float:
        req_tokens = set(self._normalize_text(requirements))
        cand_tokens = set(self._normalize_text(candidate_text))
        if not req_tokens or not cand_tokens:
            return 0.0
        common = req_tokens.intersection(cand_tokens)
        return len(common) / len(req_tokens)

    def _extract_matching_terms(self, requirements: str, candidate_text: str) -> list[str]:
        stopwords = {'de', 'y', 'en', 'el', 'la', 'los', 'las', 'para', 'con', 'por', 'del', 'al', 'un', 'una', 'su', 'sus', 'a', 'o', 'e', 'u'}
        
        # Normalize and get single word tokens from requirements, filtering stopwords
        req_tokens = [token for token in self._normalize_text(requirements) if token not in stopwords]
        cand_tokens = set(self._normalize_text(candidate_text))
        
        matched = []
        seen = set()

        # Extract common bigrams (two-word phrases) from requirements
        req_bigrams = []
        req_words_lower = requirements.lower().split()
        for i in range(len(req_words_lower) - 1):
            bigram = f"{req_words_lower[i]} {req_words_lower[i+1]}"
            # Only consider bigrams if neither word is a stopword and it's not just two stopwords
            if not (req_words_lower[i] in stopwords and req_words_lower[i+1] in stopwords):
                req_bigrams.append(bigram)

        # Prioritize matching bigrams
        candidate_text_lower = candidate_text.lower()
        for bigram in req_bigrams:
            if bigram in candidate_text_lower and bigram not in seen:
                seen.add(bigram)
                matched.append(bigram)
                if len(matched) >= 12: # Limit the number of matched terms for display
                    break

        # Then match single words
        for token in req_tokens: # Use the filtered req_tokens
            if token in cand_tokens and token not in seen and token not in stopwords: # Ensure single words are not stopwords
                seen.add(token)
                matched.append(token)
                if len(matched) >= 12:
                    break
        return matched

    def _safe_int_score(self, value: any) -> int:
        try:
            return int(float(value))
        except Exception:
            return 0

    def _build_local_candidate_profile(self, cv_data: Dict[str, str]) -> str:
        parts = [cv_data.get('name', ''), cv_data.get('education', ''), cv_data.get('experience', ''), cv_data.get('skills', ''), cv_data.get('raw_text', '')]
        return ' '.join([part for part in parts if part])

    def extract_job_requirements_from_url(self, url: str) -> str:
        """Extrae el texto de requisitos desde una página web pública."""
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            response = requests.get(url, timeout=15, headers=headers)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

            keywords = ["vacante", "vacantes", "trabaja", "requisitos", "perfil", "puesto", "oferta", "contratación"]
            texts = []
            for tag in soup.find_all(["h1", "h2", "h3", "h4", "h5", "p", "li", "span", "div"]):
                text = tag.get_text(separator=" ", strip=True)
                if not text:
                    continue
                lower = text.lower()
                if any(keyword in lower for keyword in keywords):
                    texts.append(text)

            if not texts:
                return soup.get_text(separator="\n", strip=True)

            return "\n\n".join(texts)
        except Exception as e:
            logger.error(f"Error extrayendo requisitos desde URL {url}: {e}")
            return ""

    def match_cv_to_job(self, cv_data: Dict[str, str], job_title: str, job_description: str) -> Dict[str, any]:
        """Usa Gemini para determinar si un CV se ajusta a una vacante con análisis detallado."""
        candidate_info = {
            'name': cv_data.get('name', ''),
            'education': cv_data.get('education', ''),
            'experience': cv_data.get('experience', ''),
            'skills': cv_data.get('skills', ''),
            'languages': cv_data.get('languages', ''),
            'certifications': cv_data.get('certifications', ''),
            'summary': cv_data.get('summary', '')
        }

        prompt = f"""
        Analiza si el siguiente candidato es adecuado para el puesto descrito.

        PUESTO DE TRABAJO:
        Título: {job_title}
        Descripción: {job_description}

        CANDIDATO:
        {json.dumps(candidate_info, ensure_ascii=False)}

        INSTRUCCIONES:
        - Evalúa experiencia, educación, habilidades, idiomas y certificaciones.
        - Describe claramente fortalezas y brechas.
        - Calcula un puntaje de coincidencia del 0 al 100.
        - Responde ÚNICAMENTE con un objeto JSON válido sin texto adicional.

        Formato de salida:
        {{
            "match": true,
            "score": 85,
            "reasoning": "...",
            "strengths": ["..."],
            "gaps": ["..."]
        }}
        """

        local_profile = self._build_local_candidate_profile(cv_data)
        local_score = self._safe_int_score(self._score_candidate_against_requirements(f"{job_title} {job_description}", local_profile) * 100)
        matched_terms = self._extract_matching_terms(f"{job_title} {job_description}", local_profile)

        if model is None:
            logger.info("API de Gemini no disponible, usando solo análisis local")
            result = {
                'match': local_score >= 70,
                'score': local_score,
                'reasoning': f'Análisis local: {local_score}% de coincidencia basada en términos clave.',
                'strengths': ['Coincidencia de términos clave entre el CV y la vacante'],
                'gaps': ['Análisis limitado sin IA - se recomienda experiencia específica'],
                'matched_terms': matched_terms
            }
            return result

        try:
            response = model.generate_content(
                contents=prompt
            )
            response_text = response.text.strip()
            result = self._parse_json_response(response_text)
            result.setdefault('match', False)
            result.setdefault('score', 0)
            result.setdefault('reasoning', 'Análisis no disponible')
            result.setdefault('strengths', [])
            result.setdefault('gaps', [])
            result.setdefault('matched_terms', matched_terms)
        except Exception as e:
            logger.error(f"Error en matching: {e}")
            result = {
                'match': False,
                'score': 0,
                'reasoning': f'No se pudo obtener análisis de Gemini: {str(e)}',
                'strengths': [],
                'gaps': [],
                'matched_terms': matched_terms
            }

        ai_score = self._safe_int_score(result.get('score', 0))
        final_score = max(ai_score, local_score)
        result['score'] = final_score
        result['match'] = result.get('match', False) or final_score >= 70
        result['matched_terms'] = result.get('matched_terms', matched_terms)

        if final_score >= 70 and not result.get('reasoning'):
            result['reasoning'] = 'El perfil tiene coincidencias claras con los términos de la vacante y cumple con los requisitos principales.'

        if local_score > ai_score and not result.get('strengths'):
            result['strengths'] = [
                'Coincidencia de términos clave entre el CV y la vacante',
                'Experiencia o habilidades relevantes detectadas en el texto completo'
            ]

        if final_score < 70 and not result.get('gaps'):
            result['gaps'] = ['El perfil necesita más experiencia específica o habilidades clave para este puesto.']

        return result

    def store_information(self, info: Dict[str, str]):
        """Almacena la información extraída en la base de datos."""
        if self.conn:
            try:
                cursor = self.conn.cursor()
                cursor.execute('''
                    INSERT INTO candidates (name, contact, education, experience, skills)
                    VALUES (?, ?, ?, ?, ?)
                ''', (info["name"], info["contact"], info["education"], info["experience"], info["skills"]))
                self.conn.commit()
                print("Información almacenada exitosamente.")
            except Error as e:
                print(e)

    def process_resume(self, file_path: str):
        """Procesa un CV: lee, extrae y almacena."""
        try:
            if file_path.endswith(".pdf"):
                text = self.read_pdf(file_path)
            elif file_path.endswith(".docx"):
                text = self.read_word(file_path)
            else:
                raise ValueError("Formato de archivo no soportado. Usa PDF o DOCX.")

            info = self.extract_information(text)
            self.store_information(info)
            return info
        except Exception as e:
            return {"error": str(e)}

    def search_candidates(self, skill: Optional[str] = None, experience_keywords: Optional[str] = None) -> list:
        """Busca y filtra candidatos en la base de datos."""
        if self.conn:
            query = "SELECT * FROM candidates WHERE 1=1"
            params = []
            
            if skill:
                query += " AND skills LIKE ?"
                params.append(f"%{skill}%")
            
            if experience_keywords:
                query += " AND experience LIKE ?"
                params.append(f"%{experience_keywords}%")
            
            cursor = self.conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchall()
        return []

    def score_resume(self, resume_data: dict, job_description: str) -> float:
        prompt = f"Evalúa la coincidencia del CV con la vacante (0-100): {job_description}. Datos CV: {json.dumps(resume_data)}"
        # The previous line was a duplicate prompt assignment and an overwritten response.
        # This function should return a float score.

        # Modified prompt to explicitly ask for only the score number.
        prompt = f"Evalúa la coincidencia del CV con la vacante (0-100). Responde ÚNICAMENTE con el número del score. Vacante: {job_description}. Datos CV: {json.dumps(resume_data, ensure_ascii=False)}"

        if model is None:
            logger.info("API de Gemini no disponible para scoring, retornando 0.0")
            return 0.0

        try:
            response = model.generate_content(contents=prompt)
            score_text = response.text.strip()
            try:
                return float(score_text)
            except ValueError:
                logger.error(f"Gemini devolvió un puntaje no numérico en score_resume: {score_text}")
                return 0.0
        except Exception as e:
            logger.error(f"Error getting score from Gemini in score_resume: {e}")
            return 0.0