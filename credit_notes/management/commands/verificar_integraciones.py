from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from pydantic import BaseModel

from credit_notes.ai_services import GeminiServiceError, _call_gemini


class Command(BaseCommand):
    help = "Verifica PostgreSQL/Neon y, opcionalmente, la conexión con Gemini."

    def add_arguments(self, parser):
        parser.add_argument(
            "--gemini",
            action="store_true",
            help="Realiza una llamada mínima a Gemini.",
        )

    def handle(self, *args, **options):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_database(), current_user")
                database_name, database_user = cursor.fetchone()
        except Exception as exc:
            raise CommandError(f"No fue posible conectar con PostgreSQL: {exc}") from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"PostgreSQL conectado: base={database_name}, usuario={database_user}"
            )
        )

        if not options["gemini"]:
            self.stdout.write("Gemini no fue consultado. Usa --gemini para probarlo.")
            return

        class HealthResponse(BaseModel):
            estado: str

        try:
            result = _call_gemini(
                'Responde únicamente con JSON y el campo "estado" igual a "ok".',
                HealthResponse,
            )
        except GeminiServiceError as exc:
            raise CommandError(f"Gemini no está disponible: {exc}") from exc

        if result.estado.lower() != "ok":
            raise CommandError(
                f"Gemini respondió, pero el valor recibido fue: {result.estado!r}"
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"Gemini conectado correctamente con el modelo {settings.GEMINI_MODEL}."
            )
        )
