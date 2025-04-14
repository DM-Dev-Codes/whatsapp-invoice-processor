# Use the shared base image
FROM base

# Copy shared modules
COPY shared /app/shared

# Copy service-specific code
COPY services/whatsapp_webhook_service /app/

# Install curl for health checks
RUN apt-get update && apt-get install -y curl


# Run the service
CMD ["python", "main.py"]
