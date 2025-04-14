# Use the shared base image
FROM base

# Copy shared modules
COPY shared /app/shared

# Copy service-specific code
COPY services/client_response_service /app/

# Run the service
CMD ["python", "main.py"]
