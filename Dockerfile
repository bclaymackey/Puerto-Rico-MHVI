# The partner branch's requirements (pandas >= 3, numpy >= 2.4) need
# Python 3.11 or newer; 3.12 is a well-supported choice.
FROM python:3.12-slim

# Hugging Face Spaces runs the container as user 1000.
RUN useradd -m -u 1000 user
WORKDIR /home/user/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --upgrade -r requirements.txt

COPY --chown=user . .
USER user

ENV PORT=7860
EXPOSE 7860
CMD ["python", "MHVIM_Dashboard_App.py"]
