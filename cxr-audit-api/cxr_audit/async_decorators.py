from lib_audit_cxr_v2 import CXRClassifier
import pandas as pd
import numpy as np
import os
import re
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from typing import Dict, List, Tuple, Optional, Callable, Any, Union
from functools import wraps
import time
from tqdm import tqdm


# ============================================================================
# GENERALIZED BATCH PROCESSING DECORATOR
# ============================================================================

class BatchProcessorConfig:
    """Configuration for batch processing."""
    
    _default_max_workers: int = 5
    _default_rate_limit_delay: float = 0.1
    
    @classmethod
    def set_default_workers(cls, workers: int):
        """Set the default number of workers for all batch processors."""
        if workers < 1:
            raise ValueError("Number of workers must be at least 1")
        cls._default_max_workers = workers
    
    @classmethod
    def set_default_rate_limit(cls, delay: float):
        """Set the default rate limit delay for all batch processors."""
        if delay < 0:
            raise ValueError("Rate limit delay must be non-negative")
        cls._default_rate_limit_delay = delay
    
    @classmethod
    def get_default_workers(cls) -> int:
        return cls._default_max_workers
    
    @classmethod
    def get_default_rate_limit(cls) -> float:
        return cls._default_rate_limit_delay


def batch_process(
    max_workers: Optional[int] = None,
    rate_limit_delay: Optional[float] = None,
    description: str = "Processing",
    error_handler: Optional[Callable[[Exception, int], Any]] = None
):
    """
    Decorator to convert a single-row processing function into a batch processor.
    
    The decorated function should accept a row (dict or Series) and return a result.
    The wrapper will handle concurrent execution, progress tracking, and error handling.
    
    Args:
        max_workers: Maximum number of concurrent workers. If None, uses BatchProcessorConfig default.
        rate_limit_delay: Delay between requests. If None, uses BatchProcessorConfig default.
        description: Description for the progress bar.
        error_handler: Optional function to handle errors. Receives (exception, index) and returns default value.
    
    Usage:
        @batch_process(max_workers=10, description="Custom processing")
        def process_single_row(row: pd.Series, **kwargs) -> dict:
            # Your processing logic here
            return {'result': some_value}
        
        # Call with a DataFrame
        results_df = process_single_row(df, input_columns=['col1', 'col2'], extra_param=value)
    
    Returns:
        A wrapper function that processes a DataFrame and returns results.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(
            df: pd.DataFrame,
            input_columns: Optional[List[str]] = None,
            output_columns: Optional[List[str]] = None,
            workers: Optional[int] = None,
            delay: Optional[float] = None,
            show_progress: bool = True,
            **kwargs
        ) -> pd.DataFrame:
            """
            Process a DataFrame using the decorated function concurrently.
            
            Args:
                df: Input DataFrame to process.
                input_columns: Columns to pass to the processing function. If None, passes entire row.
                output_columns: Expected output columns. If None, infers from first result.
                workers: Override max_workers for this call.
                delay: Override rate_limit_delay for this call.
                show_progress: Whether to show progress bar.
                **kwargs: Additional arguments passed to the processing function.
            
            Returns:
                DataFrame with original data plus new columns from processing.
            """
            # Resolve configuration
            effective_workers = workers or max_workers or BatchProcessorConfig.get_default_workers()
            effective_delay = delay if delay is not None else (
                rate_limit_delay if rate_limit_delay is not None else BatchProcessorConfig.get_default_rate_limit()
            )
            
            print(f"{description}: Processing {len(df)} rows using {effective_workers} workers...")
            
            df_result = df.copy()
            results: Dict[Any, Any] = {}
            
            def process_with_rate_limit(row_data: dict, index: Any) -> Tuple[Any, Any]:
                """Wrapper to add rate limiting and error handling."""
                try:
                    if effective_delay > 0:
                        time.sleep(effective_delay)
                    result = func(row_data, **kwargs)
                    return index, result
                except Exception as e:
                    print(f"Error processing row {index}: {e}")
                    if error_handler:
                        return index, error_handler(e, index)
                    return index, {}
            
            with ThreadPoolExecutor(max_workers=effective_workers) as executor:
                # Prepare row data
                future_to_index: Dict[Any, Any] = {}
                for idx, row in df.iterrows():
                    if input_columns:
                        row_data = {col: row[col] for col in input_columns if col in row.index}
                    else:
                        row_data = row.to_dict()
                    
                    future = executor.submit(process_with_rate_limit, row_data, idx)
                    future_to_index[future] = idx
                
                # Collect results
                iterator = as_completed(future_to_index)
                if show_progress:
                    iterator = tqdm(iterator, total=len(future_to_index), desc=description)
                
                for future in iterator:
                    try:
                        index, result = future.result()
                        results[index] = result
                    except Exception as e:
                        index = future_to_index[future]
                        print(f"Error in future for index {index}: {e}")
                        results[index] = {}
            
            # Convert results to DataFrame columns
            if results:
                # Get first non-empty result to determine columns
                first_result = next((r for r in results.values() if r), {})
                
                if isinstance(first_result, dict):
                    columns_to_add = output_columns or list(first_result.keys())
                    for col in columns_to_add:
                        df_result[col] = [results.get(idx, {}).get(col, None) for idx in df.index]
                else:
                    # Single value result
                    col_name = output_columns[0] if output_columns else 'result'
                    df_result[col_name] = [results.get(idx, None) for idx in df.index]
            
            return df_result
        
        return wrapper
    
    return decorator


def batch_process_simple(
    func: Callable[[Any], Any],
    items: List[Any],
    max_workers: Optional[int] = None,
    rate_limit_delay: Optional[float] = None,
    description: str = "Processing",
    error_default: Any = None,
    show_progress: bool = True
) -> List[Any]:
    """
    Simple batch processing function for lists (non-decorator version).
    
    Args:
        func: Function to apply to each item.
        items: List of items to process.
        max_workers: Maximum number of concurrent workers.
        rate_limit_delay: Delay between requests.
        description: Description for progress bar.
        error_default: Default value to return on error.
        show_progress: Whether to show progress bar.
    
    Returns:
        List of results in the same order as input items.
    """
    effective_workers = max_workers or BatchProcessorConfig.get_default_workers()
    effective_delay = rate_limit_delay if rate_limit_delay is not None else BatchProcessorConfig.get_default_rate_limit()
    
    print(f"{description}: Processing {len(items)} items using {effective_workers} workers...")
    
    results = [None] * len(items)
    
    def process_with_rate_limit(item: Any, index: int) -> Tuple[int, Any]:
        try:
            if effective_delay > 0:
                time.sleep(effective_delay)
            return index, func(item)
        except Exception as e:
            print(f"Error processing item {index}: {e}")
            return index, error_default
    
    with ThreadPoolExecutor(max_workers=effective_workers) as executor:
        future_to_index = {
            executor.submit(process_with_rate_limit, item, i): i
            for i, item in enumerate(items)
        }
        
        iterator = as_completed(future_to_index)
        if show_progress:
            iterator = tqdm(iterator, total=len(future_to_index), desc=description)
        
        for future in iterator:
            try:
                index, result = future.result()
                results[index] = result
            except Exception as e:
                index = future_to_index[future]
                print(f"Error in future for item {index}: {e}")
                results[index] = error_default
    
    return results


# ============================================================================
# USAGE EXAMPLES
# ============================================================================

"""
USAGE EXAMPLES FOR GENERALIZED BATCH PROCESSING
================================================

1. Using the @batch_process decorator for custom processing functions:

    from grade_batch_async import batch_process, BatchProcessorConfig
    
    # Set global defaults (optional)
    BatchProcessorConfig.set_default_workers(10)
    BatchProcessorConfig.set_default_rate_limit(0.05)
    
    # Define a custom processing function with the decorator
    @batch_process(max_workers=8, description="Sentiment Analysis")
    def analyze_sentiment(row: dict, model=None) -> dict:
        text = row.get('text', '')
        # Your processing logic here
        result = model.predict(text) if model else {'sentiment': 'neutral', 'score': 0.5}
        return result
    
    # Use with a DataFrame
    df = pd.DataFrame({'text': ['Hello world', 'Great product!', 'Terrible service']})
    results_df = analyze_sentiment(df, input_columns=['text'], model=my_model)


2. Using batch_process_simple for list processing:

    from grade_batch_async import batch_process_simple
    
    def fetch_data(url):
        import requests
        response = requests.get(url)
        return response.json()
    
    urls = ['http://api.example.com/1', 'http://api.example.com/2', ...]
    results = batch_process_simple(
        func=fetch_data,
        items=urls,
        max_workers=20,
        rate_limit_delay=0.1,
        description="Fetching API data",
        error_default=None
    )


3. Changing workers at runtime for BatchCXRProcessor:

    processor = BatchCXRProcessor(
        findings_dict=findings,
        tubes_lines_dict=tubes_lines,
        diagnoses_dict=diagnoses,
        max_workers=5  # Initial setting
    )
    
    # Process first batch with 5 workers
    df1 = processor.process_semialgo_batch(df1)
    
    # Increase workers for larger batch
    processor.set_max_workers(15)
    df2 = processor.process_semialgo_batch(df2)
    
    # Check current configuration
    print(processor.get_config())


4. Override workers per-call with the decorator:

    @batch_process(max_workers=5, description="Default processing")
    def process_item(row: dict) -> dict:
        return {'processed': True}
    
    # Use default workers (5)
    result1 = process_item(df1)
    
    # Override for this specific call (use 20 workers)
    result2 = process_item(df2, workers=20)


5. Using with error handling:

    def handle_error(exception, index):
        print(f"Custom error handler: {exception} at index {index}")
        return {'error': str(exception), 'index': index}
    
    @batch_process(
        max_workers=10,
        description="Robust processing",
        error_handler=handle_error
    )
    def risky_process(row: dict) -> dict:
        if row.get('bad_data'):
            raise ValueError("Bad data detected")
        return {'result': 'success'}


6. Creating a generic text processor:

    @batch_process(max_workers=10, description="Text Processing")
    def process_text(row: dict, processor_fn=None, **kwargs) -> dict:
        text = row.get('text', '')
        if processor_fn:
            return processor_fn(text, **kwargs)
        return {'processed_text': text.strip().lower()}
    
    # Use with different processor functions
    def summarize(text, max_length=100):
        return {'summary': text[:max_length] + '...'}
    
    def translate(text, target_lang='es'):
        # Your translation logic
        return {'translated': translated_text}
    
    # Apply different processors to the same data
    summaries = process_text(df, processor_fn=summarize, max_length=50)
    translations = process_text(df, processor_fn=translate, target_lang='fr')

"""
