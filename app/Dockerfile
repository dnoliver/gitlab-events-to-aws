FROM public.ecr.aws/lambda/python:3.12

# Copy function requirements
COPY requirements.txt ${LAMBDA_TASK_ROOT}

# Install app requirements
RUN pip install -r requirements.txt --target "${LAMBDA_TASK_ROOT}"

# Copy function code
COPY app.py ${LAMBDA_TASK_ROOT}

# Command to run the Lambda function
CMD ["app.handler"]