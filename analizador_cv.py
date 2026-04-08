# Analizador de Hojas de Vida en Python
# Requisitos previos: Instalar las bibliotecas necesarias
# pip install pypdf python-docx
# Nota: SpaCy no es compatible con Python 3.14, se ha removido temporalmente
import google.genai as genai
import json
import os
import logging
import requests
from bs4 import BeautifulSoup

# Configura tu API Key
GEMINI_API_KEY = "AIzaSyBh8Jg8z5p5R7Zgk3sp1AX4bgL_6o_beKQ"
client = genai.Client(api_key=GEMINI_API_KEY)
from pypdf import PdfReader
import docx
# import spacy  # Removido por incompatibilidad con Python 3.14
import re
import sqlite3
from sqlite3 import Error
from typing import Dict, Optional

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
        Analiza el siguiente texto de un currículum vitae y extrae la información relevante de manera precisa y detallada.

        IMPORTANTE: 
        - Responde ÚNICAMENTE con un objeto JSON válido, sin texto adicional.
        - Si no encuentras información específica, usa cadena vacía "".
        - Sé específico y preciso en la extracción.
        - Para experiencia, incluye años, puestos y empresas si están disponibles.
        - Para habilidades, lista las técnicas y blandas mencionadas.

        Campos a extraer:
        - name: Nombre completo de la persona (incluyendo apellidos si están disponibles)
        - contact: Toda la información de contacto disponible (email, teléfono, dirección, LinkedIn, etc.)
        - education: Detalles completos de formación académica (títulos, instituciones, años, especializaciones)
        - experience: Historial laboral detallado (puestos, empresas, períodos, responsabilidades clave)
        - skills: Lista de habilidades técnicas y blandas identificadas en el CV

        Ejemplo de respuesta esperada:
        {{
            "name": "María González Rodríguez",
            "contact": "maria.gonzalez@email.com, +57 300 123 4567, Bogotá, Colombia",
            "education": "Ingeniería Industrial, Universidad Nacional, 2015-2020. Especialización en Gestión de Calidad",
            "experience": "Gerente de Producción en Empresa XYZ (2020-2023): Lideré equipo de 15 personas, implementé sistema de calidad ISO 9001. Analista de Procesos en ABC Corp (2018-2020): Optimizé procesos reduciendo costos en 20%",
            "skills": "Python, SQL, Gestión de Proyectos, Liderazgo de Equipos, ISO 9001, Lean Manufacturing"
        }}

        Texto del CV a analizar:
        {text}
        """

        try:
            response = client.models.generate_content(
                model='gemini-1.5-pro',
                contents=prompt
            )
            response_text = response.text.strip()
            logger.info(f"Respuesta de Gemini: {response_text[:200]}...")

            # Intentar extraer JSON de la respuesta
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                info = json.loads(json_str)
                logger.info("JSON extraído exitosamente de Gemini")
                return info
            else:
                raise ValueError("No se encontró JSON en la respuesta")

        except Exception as e:
            logger.error(f"Error en extracción con Gemini: {e}")
            # Fallback a extracción básica con regex
            logger.info("Usando extracción básica con regex")
            return self._extract_with_regex(text)

    def _extract_with_regex(self, text: str) -> Dict[str, str]:
        """Extracción básica usando expresiones regulares."""
        info = {
            "name": "",
            "contact": "",
            "education": "",
            "experience": "",
            "skills": ""
        }

        # Extraer nombre (asumiendo que está al inicio, en mayúsculas o con título)
        name_match = re.search(r'^([A-ZÁÉÍÓÚÑ\s]{2,50})', text.strip(), re.MULTILINE)
        if name_match:
            info["name"] = name_match.group(1).strip()

        # Extraer email
        email_match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', text)
        if email_match:
            info["contact"] = email_match.group(0)

        # Extraer teléfono (patrones comunes)
        phone_match = re.search(r'\b(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b', text)
        if phone_match:
            if info["contact"]:
                info["contact"] += f", {phone_match.group(0)}"
            else:
                info["contact"] = phone_match.group(0)

        # Extraer educación (palabras clave)
        education_keywords = ['educación', 'estudios', 'universidad', 'colegio', 'bachiller', 'licenciatura', 'ingeniería', 'maestría', 'doctorado']
        education_lines = []
        for line in text.split('\n'):
            if any(keyword.lower() in line.lower() for keyword in education_keywords):
                education_lines.append(line.strip())
        info["education"] = ' '.join(education_lines[:3])  # Limitar a 3 líneas

        # Extraer experiencia (palabras clave)
        experience_keywords = ['experiencia', 'trabajo', 'empleo', 'puesto', 'cargo', 'empresa', 'años', 'desarrollador', 'ingeniero']
        experience_lines = []
        for line in text.split('\n'):
            if any(keyword.lower() in line.lower() for keyword in experience_keywords):
                experience_lines.append(line.strip())
        info["experience"] = ' '.join(experience_lines[:5])  # Limitar a 5 líneas

        # Extraer habilidades (palabras clave técnicas comunes)
        skills_keywords = ['python', 'java', 'javascript', 'sql', 'html', 'css', 'react', 'node', 'git', 'linux', 'windows', 'ingles', 'español']
        found_skills = []
        for skill in skills_keywords:
            if skill.lower() in text.lower():
                found_skills.append(skill.title())
        info["skills"] = ', '.join(found_skills)

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
        prompt = f"""
        Realiza un análisis detallado para determinar si el siguiente currículum vitae es adecuado para el puesto de trabajo descrito.

        PUESTO DE TRABAJO:
        Título: {job_title}
        Descripción completa: {job_description}

        INFORMACIÓN DEL CANDIDATO:
        - Nombre: {cv_data.get('name', 'No especificado')}
        - Educación: {cv_data.get('education', 'No especificada')}
        - Experiencia laboral: {cv_data.get('experience', 'No especificada')}
        - Habilidades técnicas: {cv_data.get('skills', 'No especificadas')}
        - Información de contacto: {cv_data.get('contact', 'No especificada')}

        INSTRUCCIONES DE ANÁLISIS:
        1. Evalúa la experiencia relevante: ¿Cuántos años de experiencia tiene en áreas relacionadas?
        2. Revisa la formación académica: ¿Cumple con los requisitos educativos?
        3. Analiza las habilidades: ¿Posee las competencias técnicas necesarias?
        4. Considera el ajuste general: ¿El perfil general del candidato encaja con el puesto?

        CRITERIOS DE EVALUACIÓN:
        - Excelente ajuste: 90-100% (cumple todos los requisitos principales)
        - Bueno ajuste: 70-89% (cumple la mayoría, con algunas brechas menores)
        - Regular ajuste: 50-69% (cumple algunos requisitos, pero tiene brechas importantes)
        - Bajo ajuste: 0-49% (no cumple los requisitos principales)

        Responde ÚNICAMENTE con un objeto JSON válido con los siguientes campos:
        - match: true/false (recomienda contratar si score >= 70)
        - score: número entero del 0 al 100
        - reasoning: explicación detallada (máximo 200 palabras) de por qué el candidato es o no adecuado
        - strengths: lista de fortalezas del candidato para este puesto
        - gaps: lista de brechas o áreas de mejora identificadas

        Formato JSON exacto:
        {{
            "match": true,
            "score": 85,
            "reasoning": "El candidato tiene 3 años de experiencia en ventas y formación en administración de empresas...",
            "strengths": ["Experiencia en ventas", "Habilidades de negociación"],
            "gaps": ["Falta experiencia específica en el sector alimenticio"]
        }}
        """

        try:
            response = client.models.generate_content(
                model='gemini-1.5-pro',
                contents=prompt
            )
            response_text = response.text.strip()
            
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(0))
                # Ensure required fields
                result.setdefault('match', False)
                result.setdefault('score', 0)
                result.setdefault('reasoning', 'Análisis no disponible')
                result.setdefault('strengths', [])
                result.setdefault('gaps', [])
                return result
            else:
                return {
                    "match": False, 
                    "score": 0, 
                    "reasoning": "No se pudo analizar la compatibilidad", 
                    "strengths": [], 
                    "gaps": []
                }
        except Exception as e:
            logger.error(f"Error en matching: {e}")
            return {
                "match": False, 
                "score": 0, 
                "reasoning": f"Error en análisis: {str(e)}", 
                "strengths": [], 
                "gaps": []
            }

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

# Ejemplo de uso
if __name__ == "__main__":
    analyzer = ResumeAnalyzer()
    
    # Procesar un CV
    # analyzer.process_resume("path/to/resume.pdf")
    
    # Buscar candidatos
    results = analyzer.search_candidates(skill="Python", experience_keywords="desarrollador")
    for row in results:
        print(row)