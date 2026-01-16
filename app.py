import streamlit as st
import requests
import json
import base64
import re
import pandas as pd
from datetime import datetime
import os

# Page configuration
st.set_page_config(
    page_title="Vectara Financial Analysis",
    page_icon="📊",
    layout="wide"
)

# Initialize session state
if 'vectara_client' not in st.session_state:
    st.session_state.vectara_client = None
if 'uploaded_files_list' not in st.session_state:
    st.session_state.uploaded_files_list = []
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'connected' not in st.session_state:
    st.session_state.connected = False

# Helper Functions
class VectaraClient:
    """Custom Vectara client using REST API"""
    
    def __init__(self, api_key, customer_id, corpus_id):
        self.api_key = api_key
        self.customer_id = customer_id
        self.corpus_id = corpus_id
        self.base_url = "https://api.vectara.io/v2"
        self.headers = {
            "x-api-key": api_key,
            "Content-Type": "application/json",
            "customer-id": customer_id
        }
    
    def test_connection(self):
        """Test the connection to Vectara"""
        try:
            url = f"{self.base_url}/corpora/{self.corpus_id}"
            response = requests.get(url, headers=self.headers)
            
            if response.status_code == 200:
                return True, "Connection successful!"
            elif response.status_code == 403:
                return False, "403 Forbidden - Check your API key and permissions"
            elif response.status_code == 401:
                return False, "401 Unauthorized - Invalid API key"
            elif response.status_code == 404:
                return False, "404 Not Found - Invalid Corpus ID"
            else:
                return False, f"Error {response.status_code}: {response.text}"
        except Exception as e:
            return False, f"Connection error: {str(e)}"
    
    def upload_file(self, file_content, filename):
        """Upload a file to Vectara corpus using multipart/form-data"""
        try:
            # Use the file upload endpoint with multipart
            url = f"{self.base_url}/corpora/{self.corpus_id}/upload_file"
            
            # Prepare headers for file upload (remove Content-Type, let requests set it)
            headers = {
                "x-api-key": self.api_key,
                "customer-id": self.customer_id
            }
            
            # Prepare multipart body with explicit metadata content type
            metadata = json.dumps({
                'filename': filename,
                'upload_date': datetime.now().isoformat()
            })
            files = {
                'file': (filename, file_content, 'application/pdf'),
                # metadata must be sent as application/json (server rejects text/plain)
                'metadata': ('metadata', metadata, 'application/json')
            }
            
            response = requests.post(url, headers=headers, files=files)
            
            if response.status_code in [200, 201]:
                return True, f"Successfully uploaded: {filename}"
            elif response.status_code == 403:
                return False, f"403 Forbidden - Check corpus permissions for uploads. Response: {response.text}"
            elif response.status_code == 401:
                return False, f"401 Unauthorized - Invalid API key. Response: {response.text}"
            else:
                return False, f"Upload failed ({response.status_code}): {response.text}"
                
        except Exception as e:
            return False, f"Error uploading {filename}: {str(e)}"
    
    def upload_file_v1(self, file_content, filename):
        """Alternative upload method using v1 API - Index Document"""
        try:
            url = f"https://api.vectara.io/v1/index"
            
            headers = {
                "x-api-key": self.api_key,
                "Content-Type": "application/json",
                "customer-id": self.customer_id
            }
            
            # Convert PDF to base64
            file_base64 = base64.b64encode(file_content).decode('utf-8')
            
            # Create document payload
            payload = {
                "customer_id": int(self.customer_id),
                "corpus_id": int(self.corpus_id),
                "document": {
                    "document_id": f"doc_{datetime.now().timestamp()}_{filename}",
                    "title": filename,
                    "metadata_json": json.dumps({
                        "filename": filename,
                        "upload_date": datetime.now().isoformat()
                    }),
                    "section": [
                        {
                            "text": file_base64
                        }
                    ]
                }
            }
            
            response = requests.post(url, headers=headers, json=payload)
            
            if response.status_code in [200, 201]:
                return True, f"Successfully uploaded: {filename}"
            elif response.status_code == 403:
                return False, f"403 Error - Your API key doesn't have INDEX permission. Check API key settings in Vectara Console."
            else:
                return False, f"Upload failed ({response.status_code}): {response.text}"
                
        except Exception as e:
            return False, f"Error uploading {filename}: {str(e)}"
    
    def check_permissions(self):
        """Check what permissions this API key has"""
        try:
            # Try to list documents (requires READ permission)
            read_test = self.list_documents()
            can_read = read_test[1] is None
            
            # Check corpus info
            url = f"{self.base_url}/corpora/{self.corpus_id}"
            response = requests.get(url, headers=self.headers)
            can_view_corpus = response.status_code == 200
            
            return {
                "can_read": can_read,
                "can_view_corpus": can_view_corpus,
                "read_error": read_test[1] if not can_read else None
            }
        except Exception as e:
            return {"error": str(e)}
    
    def query(self, query_text, num_results=10):
        """Query the Vectara corpus"""
        try:
            url = f"{self.base_url}/query"
            
            payload = {
                "query": query_text,
                "search": {
                    # corpus_key only, per-corpus limit is not a valid field
                    "corpora": [{"corpus_key": self.corpus_id}],
                    "limit": num_results,
                    "offset": 0
                },
                "generation": {
                    "generation_preset_name": "vectara-summary-ext-v1.2.0",
                    "max_used_search_results": 5
                }
            }
            
            response = requests.post(url, headers=self.headers, json=payload)
            
            if response.status_code == 200:
                return response.json(), None
            elif response.status_code == 403:
                return None, f"403 Forbidden - Check query permissions: {response.text}"
            else:
                return None, f"Query failed ({response.status_code}): {response.text}"
                
        except Exception as e:
            return None, f"Error querying: {str(e)}"
    
    def list_documents(self):
        """List all documents in the corpus"""
        try:
            url = f"{self.base_url}/corpora/{self.corpus_id}/documents"
            response = requests.get(url, headers=self.headers)
            
            if response.status_code == 200:
                return response.json(), None
            else:
                return None, f"Failed to list documents ({response.status_code}): {response.text}"
                
        except Exception as e:
            return None, f"Error listing documents: {str(e)}"

def initialize_vectara(api_key, customer_id, corpus_id):
    """Initialize Vectara client with credentials"""
    try:
        client = VectaraClient(api_key, customer_id, corpus_id)
        # Test the connection
        success, message = client.test_connection()
        if success:
            return client, None
        else:
            return None, message
    except Exception as e:
        return None, str(e)

def extract_metrics_from_response(response_data, metric_names=None):
    """Extract financial metrics from Vectara response"""
    if metric_names is None:
        metric_names = ["Revenue", "Net Profit", "Gross Profit", "Total Assets", "Total Liabilities"]
    
    metrics = {name: "N/A" for name in metric_names}
    
    if response_data and 'search_results' in response_data:
        combined_text = ""
        for result in response_data['search_results'][:5]:
            if 'text' in result:
                combined_text += " " + result['text']
        
        for metric in metric_names:
            # Try different patterns
            patterns = [
                rf"{metric}\s*[:\-]?\s*\$?\s*(\d{{1,3}}(?:,\d{{3}})*(?:\.\d{{2}})?)",
                rf"{metric}\s*\(?\$?(\d{{1,3}}(?:,\d{{3}})*(?:\.\d{{2}})?)\)?",
            ]
            
            for pattern in patterns:
                match = re.search(pattern, combined_text, re.IGNORECASE)
                if match:
                    metrics[metric] = match.group(1).replace(",", "")
                    break
    
    return metrics

# Main App Layout
st.title("📊 Vectara Financial Analysis Dashboard")
st.markdown("Upload financial documents, query them intelligently, and compare metrics across multiple files.")

# Sidebar for configuration
with st.sidebar:
    st.header("⚙️ Configuration")
    
    # Troubleshooting tips
    with st.expander("❓ Troubleshooting 403 Errors"):
        st.markdown("""
        **Common causes of 403 Forbidden errors:**
        
        1. **Wrong API Key Type**: Make sure you're using a **Personal API Key**, not OAuth credentials
        2. **Missing INDEX Permission**: Your API key needs **INDEX** permission to upload documents
        3. **Incorrect Corpus ID**: Verify the corpus ID exists and you have access
        4. **Wrong Customer ID**: Double-check your customer ID matches your account
        
        **How to fix:**
        1. Go to Vectara Console → Authorization → API Keys
        2. Either edit existing key OR create new one
        3. **IMPORTANT**: Check the "Index" checkbox under permissions
        4. Make sure the corpus "hello_world" is selected in the key's access list
        5. Copy the new API key and reconnect
        
        **Required Permissions for this app:**
        - ✅ **Query** - To search documents
        - ✅ **Index** - To upload documents (THIS IS REQUIRED!)
        - ✅ **Read** - To list documents
        
        **API Key Format**: Should look like `zut_xxxxx...` or `zwt_xxxxx...`
        """)
    
    st.divider()
    
    # Permission checker
    if st.session_state.connected and st.session_state.vectara_client:
        with st.expander("🔍 Check API Key Permissions"):
            if st.button("Test Permissions"):
                with st.spinner("Checking permissions..."):
                    perms = st.session_state.vectara_client.check_permissions()
                    
                    st.write("**Permission Test Results:**")
                    if "error" in perms:
                        st.error(f"Error: {perms['error']}")
                    else:
                        st.write(f"✅ Can view corpus: {perms['can_view_corpus']}")
                        st.write(f"✅ Can read/list documents: {perms['can_read']}")
                        
                        if not perms['can_read']:
                            st.error(f"Read error: {perms['read_error']}")
                        
                        st.warning("⚠️ Cannot test INDEX permission without uploading. If uploads fail with 403, your key is missing INDEX permission.")
    
    st.divider()
    
    # Connection inputs
    api_key = st.text_input("Vectara API Key", type="password", help="Your Personal API Key (starts with zut_ or zwt_)", key="api_key_input")
    customer_id = st.text_input("Customer ID", help="Your Vectara Customer ID", key="customer_id_input")
    corpus_id = st.text_input("Corpus ID", help="Your Vectara Corpus ID or Key", key="corpus_id_input")
    
    if st.button("Connect to Vectara", type="primary"):
        if api_key and customer_id and corpus_id:
            with st.spinner("Testing connection..."):
                client, error = initialize_vectara(api_key, customer_id, corpus_id)
                if client:
                    st.session_state.vectara_client = client
                    st.session_state.connected = True
                    st.success("✅ Connected successfully!")
                    st.rerun()
                else:
                    st.error(f"❌ Connection failed: {error}")
                    st.info("Please check the troubleshooting guide above")
        else:
            st.warning("Please fill in all fields")
    
    st.divider()
    
    # Display connection status
    if st.session_state.connected and st.session_state.vectara_client:
        st.success("🟢 Connected")
        
        # List documents in corpus
        if st.button("🔍 View Corpus Documents"):
            with st.spinner("Loading documents..."):
                docs, error = st.session_state.vectara_client.list_documents()
                if error:
                    st.error(f"Error: {error}")
                elif docs and 'documents' in docs:
                    st.write(f"**Documents in corpus:** {len(docs['documents'])}")
                    for i, doc in enumerate(docs['documents'][:10], 1):
                        doc_id = doc.get('id', 'N/A')
                        st.text(f"{i}. ID: {doc_id}")
                else:
                    st.info("No documents found")
        
        # Disconnect button
        if st.button("Disconnect", type="secondary"):
            st.session_state.vectara_client = None
            st.session_state.connected = False
            st.rerun()
    else:
        st.warning("🔴 Not Connected")

# Main content area with tabs
tab1, tab2, tab3 = st.tabs(["📤 Upload Files", "💬 Query Documents", "📈 Financial Comparison"])

# Tab 1: Upload Files
with tab1:
    st.header("Upload PDF Documents")
    
    if not st.session_state.connected:
        st.warning("⚠️ Please connect to Vectara first using the sidebar.")
    else:
        # Upload method selector
        upload_method = st.radio(
            "Select upload method:",
            ["V2 API (Recommended)", "V1 API (Alternative)"],
            help="Try V1 API if V2 gives 403 errors"
        )
        
        uploaded_files = st.file_uploader(
            "Choose PDF files",
            type=['pdf'],
            accept_multiple_files=True,
            help="Upload one or more PDF files to analyze",
            key="pdf_uploader"
        )
        
        if uploaded_files and st.button("📤 Upload to Vectara", type="primary", key="upload_btn"):
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            success_count = 0
            total_files = len(uploaded_files)
            
            client = st.session_state.vectara_client
            
            for i, file in enumerate(uploaded_files):
                status_text.text(f"Uploading {file.name}...")
                
                # Read file content
                file_content = file.read()
                
                # Choose upload method
                if upload_method == "V1 API (Alternative)":
                    success, message = client.upload_file_v1(file_content, file.name)
                else:
                    success, message = client.upload_file(file_content, file.name)
                
                if success:
                    st.success(message)
                    success_count += 1
                    if file.name not in st.session_state.uploaded_files_list:
                        st.session_state.uploaded_files_list.append(file.name)
                else:
                    st.error(message)
                
                progress_bar.progress((i + 1) / total_files)
            
            status_text.text(f"Upload complete! {success_count}/{total_files} files uploaded successfully.")
        
        # Display uploaded files
        if st.session_state.uploaded_files_list:
            st.subheader("📋 Uploaded Files")
            for i, filename in enumerate(st.session_state.uploaded_files_list, 1):
                st.text(f"{i}. {filename}")

# Tab 2: Query Documents
with tab2:
    st.header("Ask Questions About Your Documents")
    
    if not st.session_state.connected:
        st.warning("⚠️ Please connect to Vectara first using the sidebar.")
    else:
        # Query input
        query_input = st.text_area(
            "Enter your question:",
            placeholder="e.g., What is the total revenue in FY2024?",
            height=100,
            key="query_input"
        )
        
        col1, col2 = st.columns([1, 5])
        with col1:
            query_button = st.button("🔍 Search", type="primary", key="search_btn")
        with col2:
            if st.button("🗑️ Clear History", key="clear_btn"):
                st.session_state.chat_history = []
                st.rerun()
        
        if query_button and query_input:
            with st.spinner("Searching..."):
                client = st.session_state.vectara_client
                response, error = client.query(query_input)
                
                if error:
                    st.error(f"Query error: {error}")
                else:
                    # Add to chat history
                    st.session_state.chat_history.append({
                        'timestamp': datetime.now().strftime("%H:%M:%S"),
                        'query': query_input,
                        'response': response
                    })
                    st.rerun()
        
        # Display chat history
        if st.session_state.chat_history:
            st.divider()
            st.subheader("💬 Conversation History")
            
            for i, chat in enumerate(reversed(st.session_state.chat_history)):
                with st.container():
                    st.markdown(f"**🕐 {chat['timestamp']}**")
                    st.markdown(f"**Q:** {chat['query']}")
                    
                    # Display generated summary
                    if 'summary' in chat['response']:
                        st.markdown(f"**A:** {chat['response']['summary']}")
                    
                    # Display search results
                    if 'search_results' in chat['response']:
                        with st.expander("📄 View Source Snippets"):
                            for j, result in enumerate(chat['response']['search_results'][:3], 1):
                                score = result.get('score', 0)
                                text = result.get('text', 'N/A')
                                st.markdown(f"**Source {j}** (Score: {score:.3f})")
                                st.text(text[:300] + "..." if len(text) > 300 else text)
                                st.markdown("---")
                    
                    st.divider()

# Tab 3: Financial Comparison
with tab3:
    st.header("Compare Financial Metrics Across Documents")
    
    if not st.session_state.connected:
        st.warning("⚠️ Please connect to Vectara first using the sidebar.")
    else:
        st.markdown("**Select metrics to compare:**")
        
        # Metrics to extract
        default_metrics = ["Revenue", "Net Profit", "Gross Profit", "Total Assets"]
        custom_metrics = st.text_input(
            "Additional metrics (comma-separated):",
            placeholder="e.g., Operating Expenses, Cash Flow",
            key="custom_metrics_input"
        )
        
        all_metrics = default_metrics.copy()
        if custom_metrics:
            all_metrics.extend([m.strip() for m in custom_metrics.split(',')])
        
        # Query for each metric
        if st.button("📊 Generate Comparison", type="primary", key="comparison_btn"):
            with st.spinner("Extracting financial metrics..."):
                client = st.session_state.vectara_client
                comparison_data = {}
                
                # Query for all metrics at once
                query_text = f"financial statements showing: {', '.join(all_metrics)}"
                response, error = client.query(query_text, num_results=10)
                
                if not error and response:
                    metrics = extract_metrics_from_response(response, all_metrics)
                    comparison_data['Document Analysis'] = metrics
                    
                    # Create comparison DataFrame
                    if comparison_data:
                        df = pd.DataFrame(comparison_data)
                        df.index.name = 'Metric'
                        
                        st.subheader("📋 Metrics Summary")
                        st.dataframe(df, use_container_width=True)
                        
                        # Convert to numeric for visualization
                        df_numeric = df.copy()
                        for col in df_numeric.columns:
                            df_numeric[col] = pd.to_numeric(df_numeric[col], errors='coerce')
                        
                        # Chart visualization
                        st.subheader("📊 Visual Comparison")
                        chart_metric = st.selectbox("Select metric to visualize:", all_metrics, key="chart_metric_select")
                        
                        if chart_metric in df_numeric.index:
                            chart_data = df_numeric.loc[chart_metric].dropna()
                            if not chart_data.empty:
                                st.bar_chart(chart_data)
                            else:
                                st.info("No numeric data available for this metric.")
                        
                        # Download option
                        csv = df.to_csv()
                        st.download_button(
                            label="📥 Download Comparison as CSV",
                            data=csv,
                            file_name="financial_comparison.csv",
                            mime="text/csv",
                            key="download_csv_btn"
                        )
                else:
                    st.error(f"Error extracting metrics: {error}")

# Footer
st.divider()
st.markdown("""
<div style='text-align: center; color: gray; font-size: 0.9em;'>
    <p>Vectara Financial Analysis Dashboard | Powered by Vectara RAG</p>
</div>
""", unsafe_allow_html=True)



# this upload the file on vectra now

# import streamlit as st
# import requests
# import json
# import base64
# import re
# import pandas as pd
# from datetime import datetime
# import os

# # Page configuration
# st.set_page_config(
#     page_title="Vectara Financial Analysis",
#     page_icon="📊",
#     layout="wide"
# )

# # Initialize session state
# if 'vectara_client' not in st.session_state:
#     st.session_state.vectara_client = None
# if 'uploaded_files_list' not in st.session_state:
#     st.session_state.uploaded_files_list = []
# if 'chat_history' not in st.session_state:
#     st.session_state.chat_history = []
# if 'connected' not in st.session_state:
#     st.session_state.connected = False

# # Helper Functions
# class VectaraClient:
#     """Custom Vectara client using REST API"""
    
#     def __init__(self, api_key, customer_id, corpus_id):
#         self.api_key = api_key
#         self.customer_id = customer_id
#         self.corpus_id = corpus_id
#         self.base_url = "https://api.vectara.io/v2"
#         self.headers = {
#             "x-api-key": api_key,
#             "Content-Type": "application/json",
#             "customer-id": customer_id
#         }
    
#     def test_connection(self):
#         """Test the connection to Vectara"""
#         try:
#             url = f"{self.base_url}/corpora/{self.corpus_id}"
#             response = requests.get(url, headers=self.headers)
            
#             if response.status_code == 200:
#                 return True, "Connection successful!"
#             elif response.status_code == 403:
#                 return False, "403 Forbidden - Check your API key and permissions"
#             elif response.status_code == 401:
#                 return False, "401 Unauthorized - Invalid API key"
#             elif response.status_code == 404:
#                 return False, "404 Not Found - Invalid Corpus ID"
#             else:
#                 return False, f"Error {response.status_code}: {response.text}"
#         except Exception as e:
#             return False, f"Connection error: {str(e)}"
    
#     def upload_file(self, file_content, filename):
#         """Upload a file to Vectara corpus using multipart/form-data"""
#         try:
#             # Use the file upload endpoint with multipart
#             url = f"{self.base_url}/corpora/{self.corpus_id}/upload_file"
            
#             # Prepare headers for file upload (remove Content-Type, let requests set it)
#             headers = {
#                 "x-api-key": self.api_key,
#                 "customer-id": self.customer_id
#             }
            
#             # Prepare multipart body with explicit metadata content type
#             metadata = json.dumps({
#                 'filename': filename,
#                 'upload_date': datetime.now().isoformat()
#             })
#             files = {
#                 'file': (filename, file_content, 'application/pdf'),
#                 # metadata must be sent as application/json (server rejects text/plain)
#                 'metadata': ('metadata', metadata, 'application/json')
#             }
            
#             response = requests.post(url, headers=headers, files=files)
            
#             if response.status_code in [200, 201]:
#                 return True, f"Successfully uploaded: {filename}"
#             elif response.status_code == 403:
#                 return False, f"403 Forbidden - Check corpus permissions for uploads. Response: {response.text}"
#             elif response.status_code == 401:
#                 return False, f"401 Unauthorized - Invalid API key. Response: {response.text}"
#             else:
#                 return False, f"Upload failed ({response.status_code}): {response.text}"
                
#         except Exception as e:
#             return False, f"Error uploading {filename}: {str(e)}"
    
#     def upload_file_v1(self, file_content, filename):
#         """Alternative upload method using v1 API - Index Document"""
#         try:
#             url = f"https://api.vectara.io/v1/index"
            
#             headers = {
#                 "x-api-key": self.api_key,
#                 "Content-Type": "application/json",
#                 "customer-id": self.customer_id
#             }
            
#             # Convert PDF to base64
#             file_base64 = base64.b64encode(file_content).decode('utf-8')
            
#             # Create document payload
#             payload = {
#                 "customer_id": int(self.customer_id),
#                 "corpus_id": int(self.corpus_id),
#                 "document": {
#                     "document_id": f"doc_{datetime.now().timestamp()}_{filename}",
#                     "title": filename,
#                     "metadata_json": json.dumps({
#                         "filename": filename,
#                         "upload_date": datetime.now().isoformat()
#                     }),
#                     "section": [
#                         {
#                             "text": file_base64
#                         }
#                     ]
#                 }
#             }
            
#             response = requests.post(url, headers=headers, json=payload)
            
#             if response.status_code in [200, 201]:
#                 return True, f"Successfully uploaded: {filename}"
#             elif response.status_code == 403:
#                 return False, f"403 Error - Your API key doesn't have INDEX permission. Check API key settings in Vectara Console."
#             else:
#                 return False, f"Upload failed ({response.status_code}): {response.text}"
                
#         except Exception as e:
#             return False, f"Error uploading {filename}: {str(e)}"
    
#     def check_permissions(self):
#         """Check what permissions this API key has"""
#         try:
#             # Try to list documents (requires READ permission)
#             read_test = self.list_documents()
#             can_read = read_test[1] is None
            
#             # Check corpus info
#             url = f"{self.base_url}/corpora/{self.corpus_id}"
#             response = requests.get(url, headers=self.headers)
#             can_view_corpus = response.status_code == 200
            
#             return {
#                 "can_read": can_read,
#                 "can_view_corpus": can_view_corpus,
#                 "read_error": read_test[1] if not can_read else None
#             }
#         except Exception as e:
#             return {"error": str(e)}
    
#     def query(self, query_text, num_results=10):
#         """Query the Vectara corpus"""
#         try:
#             url = f"{self.base_url}/query"
            
#             payload = {
#                 "query": query_text,
#                 "search": {
#                     "corpora": [
#                         {
#                             "corpus_key": self.corpus_id,
#                             "limit": num_results
#                         }
#                     ],
#                     "limit": num_results
#                 },
#                 "generation": {
#                     "generation_preset_name": "vectara-summary-ext-v1.2.0",
#                     "max_used_search_results": 5
#                 }
#             }
            
#             response = requests.post(url, headers=self.headers, json=payload)
            
#             if response.status_code == 200:
#                 return response.json(), None
#             elif response.status_code == 403:
#                 return None, f"403 Forbidden - Check query permissions: {response.text}"
#             else:
#                 return None, f"Query failed ({response.status_code}): {response.text}"
                
#         except Exception as e:
#             return None, f"Error querying: {str(e)}"
    
#     def list_documents(self):
#         """List all documents in the corpus"""
#         try:
#             url = f"{self.base_url}/corpora/{self.corpus_id}/documents"
#             response = requests.get(url, headers=self.headers)
            
#             if response.status_code == 200:
#                 return response.json(), None
#             else:
#                 return None, f"Failed to list documents ({response.status_code}): {response.text}"
                
#         except Exception as e:
#             return None, f"Error listing documents: {str(e)}"

# def initialize_vectara(api_key, customer_id, corpus_id):
#     """Initialize Vectara client with credentials"""
#     try:
#         client = VectaraClient(api_key, customer_id, corpus_id)
#         # Test the connection
#         success, message = client.test_connection()
#         if success:
#             return client, None
#         else:
#             return None, message
#     except Exception as e:
#         return None, str(e)

# def extract_metrics_from_response(response_data, metric_names=None):
#     """Extract financial metrics from Vectara response"""
#     if metric_names is None:
#         metric_names = ["Revenue", "Net Profit", "Gross Profit", "Total Assets", "Total Liabilities"]
    
#     metrics = {name: "N/A" for name in metric_names}
    
#     if response_data and 'search_results' in response_data:
#         combined_text = ""
#         for result in response_data['search_results'][:5]:
#             if 'text' in result:
#                 combined_text += " " + result['text']
        
#         for metric in metric_names:
#             # Try different patterns
#             patterns = [
#                 rf"{metric}\s*[:\-]?\s*\$?\s*(\d{{1,3}}(?:,\d{{3}})*(?:\.\d{{2}})?)",
#                 rf"{metric}\s*\(?\$?(\d{{1,3}}(?:,\d{{3}})*(?:\.\d{{2}})?)\)?",
#             ]
            
#             for pattern in patterns:
#                 match = re.search(pattern, combined_text, re.IGNORECASE)
#                 if match:
#                     metrics[metric] = match.group(1).replace(",", "")
#                     break
    
#     return metrics

# # Main App Layout
# st.title("📊 Vectara Financial Analysis Dashboard")
# st.markdown("Upload financial documents, query them intelligently, and compare metrics across multiple files.")

# # Sidebar for configuration
# with st.sidebar:
#     st.header("⚙️ Configuration")
    
#     # Troubleshooting tips
#     with st.expander("❓ Troubleshooting 403 Errors"):
#         st.markdown("""
#         **Common causes of 403 Forbidden errors:**
        
#         1. **Wrong API Key Type**: Make sure you're using a **Personal API Key**, not OAuth credentials
#         2. **Missing INDEX Permission**: Your API key needs **INDEX** permission to upload documents
#         3. **Incorrect Corpus ID**: Verify the corpus ID exists and you have access
#         4. **Wrong Customer ID**: Double-check your customer ID matches your account
        
#         **How to fix:**
#         1. Go to Vectara Console → Authorization → API Keys
#         2. Either edit existing key OR create new one
#         3. **IMPORTANT**: Check the "Index" checkbox under permissions
#         4. Make sure the corpus "hello_world" is selected in the key's access list
#         5. Copy the new API key and reconnect
        
#         **Required Permissions for this app:**
#         - ✅ **Query** - To search documents
#         - ✅ **Index** - To upload documents (THIS IS REQUIRED!)
#         - ✅ **Read** - To list documents
        
#         **API Key Format**: Should look like `zut_xxxxx...` or `zwt_xxxxx...`
#         """)
    
#     st.divider()
    
#     # Permission checker
#     if st.session_state.connected and st.session_state.vectara_client:
#         with st.expander("🔍 Check API Key Permissions"):
#             if st.button("Test Permissions"):
#                 with st.spinner("Checking permissions..."):
#                     perms = st.session_state.vectara_client.check_permissions()
                    
#                     st.write("**Permission Test Results:**")
#                     if "error" in perms:
#                         st.error(f"Error: {perms['error']}")
#                     else:
#                         st.write(f"✅ Can view corpus: {perms['can_view_corpus']}")
#                         st.write(f"✅ Can read/list documents: {perms['can_read']}")
                        
#                         if not perms['can_read']:
#                             st.error(f"Read error: {perms['read_error']}")
                        
#                         st.warning("⚠️ Cannot test INDEX permission without uploading. If uploads fail with 403, your key is missing INDEX permission.")
    
#     st.divider()
    
#     # Connection inputs
#     api_key = st.text_input("Vectara API Key", type="password", help="Your Personal API Key (starts with zut_ or zwt_)", key="api_key_input")
#     customer_id = st.text_input("Customer ID", help="Your Vectara Customer ID", key="customer_id_input")
#     corpus_id = st.text_input("Corpus ID", help="Your Vectara Corpus ID or Key", key="corpus_id_input")
    
#     if st.button("Connect to Vectara", type="primary"):
#         if api_key and customer_id and corpus_id:
#             with st.spinner("Testing connection..."):
#                 client, error = initialize_vectara(api_key, customer_id, corpus_id)
#                 if client:
#                     st.session_state.vectara_client = client
#                     st.session_state.connected = True
#                     st.success("✅ Connected successfully!")
#                     st.rerun()
#                 else:
#                     st.error(f"❌ Connection failed: {error}")
#                     st.info("Please check the troubleshooting guide above")
#         else:
#             st.warning("Please fill in all fields")
    
#     st.divider()
    
#     # Display connection status
#     if st.session_state.connected and st.session_state.vectara_client:
#         st.success("🟢 Connected")
        
#         # List documents in corpus
#         if st.button("🔍 View Corpus Documents"):
#             with st.spinner("Loading documents..."):
#                 docs, error = st.session_state.vectara_client.list_documents()
#                 if error:
#                     st.error(f"Error: {error}")
#                 elif docs and 'documents' in docs:
#                     st.write(f"**Documents in corpus:** {len(docs['documents'])}")
#                     for i, doc in enumerate(docs['documents'][:10], 1):
#                         doc_id = doc.get('id', 'N/A')
#                         st.text(f"{i}. ID: {doc_id}")
#                 else:
#                     st.info("No documents found")
        
#         # Disconnect button
#         if st.button("Disconnect", type="secondary"):
#             st.session_state.vectara_client = None
#             st.session_state.connected = False
#             st.rerun()
#     else:
#         st.warning("🔴 Not Connected")

# # Main content area with tabs
# tab1, tab2, tab3 = st.tabs(["📤 Upload Files", "💬 Query Documents", "📈 Financial Comparison"])

# # Tab 1: Upload Files
# with tab1:
#     st.header("Upload PDF Documents")
    
#     if not st.session_state.connected:
#         st.warning("⚠️ Please connect to Vectara first using the sidebar.")
#     else:
#         # Upload method selector
#         upload_method = st.radio(
#             "Select upload method:",
#             ["V2 API (Recommended)", "V1 API (Alternative)"],
#             help="Try V1 API if V2 gives 403 errors"
#         )
        
#         uploaded_files = st.file_uploader(
#             "Choose PDF files",
#             type=['pdf'],
#             accept_multiple_files=True,
#             help="Upload one or more PDF files to analyze",
#             key="pdf_uploader"
#         )
        
#         if uploaded_files and st.button("📤 Upload to Vectara", type="primary", key="upload_btn"):
#             progress_bar = st.progress(0)
#             status_text = st.empty()
            
#             success_count = 0
#             total_files = len(uploaded_files)
            
#             client = st.session_state.vectara_client
            
#             for i, file in enumerate(uploaded_files):
#                 status_text.text(f"Uploading {file.name}...")
                
#                 # Read file content
#                 file_content = file.read()
                
#                 # Choose upload method
#                 if upload_method == "V1 API (Alternative)":
#                     success, message = client.upload_file_v1(file_content, file.name)
#                 else:
#                     success, message = client.upload_file(file_content, file.name)
                
#                 if success:
#                     st.success(message)
#                     success_count += 1
#                     if file.name not in st.session_state.uploaded_files_list:
#                         st.session_state.uploaded_files_list.append(file.name)
#                 else:
#                     st.error(message)
                
#                 progress_bar.progress((i + 1) / total_files)
            
#             status_text.text(f"Upload complete! {success_count}/{total_files} files uploaded successfully.")
        
#         # Display uploaded files
#         if st.session_state.uploaded_files_list:
#             st.subheader("📋 Uploaded Files")
#             for i, filename in enumerate(st.session_state.uploaded_files_list, 1):
#                 st.text(f"{i}. {filename}")

# # Tab 2: Query Documents
# with tab2:
#     st.header("Ask Questions About Your Documents")
    
#     if not st.session_state.connected:
#         st.warning("⚠️ Please connect to Vectara first using the sidebar.")
#     else:
#         # Query input
#         query_input = st.text_area(
#             "Enter your question:",
#             placeholder="e.g., What is the total revenue in FY2024?",
#             height=100,
#             key="query_input"
#         )
        
#         col1, col2 = st.columns([1, 5])
#         with col1:
#             query_button = st.button("🔍 Search", type="primary", key="search_btn")
#         with col2:
#             if st.button("🗑️ Clear History", key="clear_btn"):
#                 st.session_state.chat_history = []
#                 st.rerun()
        
#         if query_button and query_input:
#             with st.spinner("Searching..."):
#                 client = st.session_state.vectara_client
#                 response, error = client.query(query_input)
                
#                 if error:
#                     st.error(f"Query error: {error}")
#                 else:
#                     # Add to chat history
#                     st.session_state.chat_history.append({
#                         'timestamp': datetime.now().strftime("%H:%M:%S"),
#                         'query': query_input,
#                         'response': response
#                     })
#                     st.rerun()
        
#         # Display chat history
#         if st.session_state.chat_history:
#             st.divider()
#             st.subheader("💬 Conversation History")
            
#             for i, chat in enumerate(reversed(st.session_state.chat_history)):
#                 with st.container():
#                     st.markdown(f"**🕐 {chat['timestamp']}**")
#                     st.markdown(f"**Q:** {chat['query']}")
                    
#                     # Display generated summary
#                     if 'summary' in chat['response']:
#                         st.markdown(f"**A:** {chat['response']['summary']}")
                    
#                     # Display search results
#                     if 'search_results' in chat['response']:
#                         with st.expander("📄 View Source Snippets"):
#                             for j, result in enumerate(chat['response']['search_results'][:3], 1):
#                                 score = result.get('score', 0)
#                                 text = result.get('text', 'N/A')
#                                 st.markdown(f"**Source {j}** (Score: {score:.3f})")
#                                 st.text(text[:300] + "..." if len(text) > 300 else text)
#                                 st.markdown("---")
                    
#                     st.divider()

# # Tab 3: Financial Comparison
# with tab3:
#     st.header("Compare Financial Metrics Across Documents")
    
#     if not st.session_state.connected:
#         st.warning("⚠️ Please connect to Vectara first using the sidebar.")
#     else:
#         st.markdown("**Select metrics to compare:**")
        
#         # Metrics to extract
#         default_metrics = ["Revenue", "Net Profit", "Gross Profit", "Total Assets"]
#         custom_metrics = st.text_input(
#             "Additional metrics (comma-separated):",
#             placeholder="e.g., Operating Expenses, Cash Flow",
#             key="custom_metrics_input"
#         )
        
#         all_metrics = default_metrics.copy()
#         if custom_metrics:
#             all_metrics.extend([m.strip() for m in custom_metrics.split(',')])
        
#         # Query for each metric
#         if st.button("📊 Generate Comparison", type="primary", key="comparison_btn"):
#             with st.spinner("Extracting financial metrics..."):
#                 client = st.session_state.vectara_client
#                 comparison_data = {}
                
#                 # Query for all metrics at once
#                 query_text = f"financial statements showing: {', '.join(all_metrics)}"
#                 response, error = client.query(query_text, num_results=10)
                
#                 if not error and response:
#                     metrics = extract_metrics_from_response(response, all_metrics)
#                     comparison_data['Document Analysis'] = metrics
                    
#                     # Create comparison DataFrame
#                     if comparison_data:
#                         df = pd.DataFrame(comparison_data)
#                         df.index.name = 'Metric'
                        
#                         st.subheader("📋 Metrics Summary")
#                         st.dataframe(df, use_container_width=True)
                        
#                         # Convert to numeric for visualization
#                         df_numeric = df.copy()
#                         for col in df_numeric.columns:
#                             df_numeric[col] = pd.to_numeric(df_numeric[col], errors='coerce')
                        
#                         # Chart visualization
#                         st.subheader("📊 Visual Comparison")
#                         chart_metric = st.selectbox("Select metric to visualize:", all_metrics, key="chart_metric_select")
                        
#                         if chart_metric in df_numeric.index:
#                             chart_data = df_numeric.loc[chart_metric].dropna()
#                             if not chart_data.empty:
#                                 st.bar_chart(chart_data)
#                             else:
#                                 st.info("No numeric data available for this metric.")
                        
#                         # Download option
#                         csv = df.to_csv()
#                         st.download_button(
#                             label="📥 Download Comparison as CSV",
#                             data=csv,
#                             file_name="financial_comparison.csv",
#                             mime="text/csv",
#                             key="download_csv_btn"
#                         )
#                 else:
#                     st.error(f"Error extracting metrics: {error}")

# # Footer
# st.divider()
# st.markdown("""
# <div style='text-align: center; color: gray; font-size: 0.9em;'>
#     <p>Vectara Financial Analysis Dashboard | Powered by Vectara RAG</p>
# </div>
# """, unsafe_allow_html=True)



# final which stuck at uploding time


# import streamlit as st
# import requests
# import json
# import base64
# import re
# import pandas as pd
# from datetime import datetime
# import os

# # Page configuration
# st.set_page_config(
#     page_title="Vectara Financial Analysis",
#     page_icon="📊",
#     layout="wide"
# )

# # Initialize session state
# if 'vectara_client' not in st.session_state:
#     st.session_state.vectara_client = None
# if 'uploaded_files_list' not in st.session_state:
#     st.session_state.uploaded_files_list = []
# if 'chat_history' not in st.session_state:
#     st.session_state.chat_history = []
# if 'connected' not in st.session_state:
#     st.session_state.connected = False

# # Helper Functions
# class VectaraClient:
#     """Custom Vectara client using REST API"""
    
#     def __init__(self, api_key, customer_id, corpus_id):
#         self.api_key = api_key
#         self.customer_id = customer_id
#         self.corpus_id = corpus_id
#         self.base_url = "https://api.vectara.io/v2"
#         self.headers = {
#             "x-api-key": api_key,
#             "Content-Type": "application/json",
#             "customer-id": customer_id
#         }
    
#     def test_connection(self):
#         """Test the connection to Vectara"""
#         try:
#             url = f"{self.base_url}/corpora/{self.corpus_id}"
#             response = requests.get(url, headers=self.headers)
            
#             if response.status_code == 200:
#                 return True, "Connection successful!"
#             elif response.status_code == 403:
#                 return False, "403 Forbidden - Check your API key and permissions"
#             elif response.status_code == 401:
#                 return False, "401 Unauthorized - Invalid API key"
#             elif response.status_code == 404:
#                 return False, "404 Not Found - Invalid Corpus ID"
#             else:
#                 return False, f"Error {response.status_code}: {response.text}"
#         except Exception as e:
#             return False, f"Connection error: {str(e)}"
    
#     def upload_file(self, file_content, filename):
#         """Upload a file to Vectara corpus using multipart/form-data"""
#         try:
#             # Use the file upload endpoint with multipart
#             url = f"{self.base_url}/corpora/{self.corpus_id}/upload_file"
            
#             # Prepare headers for file upload (remove Content-Type, let requests set it)
#             headers = {
#                 "x-api-key": self.api_key,
#                 "customer-id": self.customer_id
#             }
            
#             # Prepare the file
#             files = {
#                 'file': (filename, file_content, 'application/pdf')
#             }
            
#             # Additional metadata
#             data = {
#                 'metadata': json.dumps({
#                     'filename': filename,
#                     'upload_date': datetime.now().isoformat()
#                 })
#             }
            
#             response = requests.post(url, headers=headers, files=files, data=data)
            
#             if response.status_code in [200, 201]:
#                 return True, f"Successfully uploaded: {filename}"
#             elif response.status_code == 403:
#                 return False, f"403 Forbidden - Check corpus permissions for uploads. Response: {response.text}"
#             elif response.status_code == 401:
#                 return False, f"401 Unauthorized - Invalid API key. Response: {response.text}"
#             else:
#                 return False, f"Upload failed ({response.status_code}): {response.text}"
                
#         except Exception as e:
#             return False, f"Error uploading {filename}: {str(e)}"
    
#     def upload_file_v1(self, file_content, filename):
#         """Alternative upload method using v1 API - Index Document"""
#         try:
#             url = f"https://api.vectara.io/v1/index"
            
#             headers = {
#                 "x-api-key": self.api_key,
#                 "Content-Type": "application/json",
#                 "customer-id": self.customer_id
#             }
            
#             # Convert PDF to base64
#             file_base64 = base64.b64encode(file_content).decode('utf-8')
            
#             # Create document payload
#             payload = {
#                 "customer_id": int(self.customer_id),
#                 "corpus_id": int(self.corpus_id),
#                 "document": {
#                     "document_id": f"doc_{datetime.now().timestamp()}_{filename}",
#                     "title": filename,
#                     "metadata_json": json.dumps({
#                         "filename": filename,
#                         "upload_date": datetime.now().isoformat()
#                     }),
#                     "section": [
#                         {
#                             "text": file_base64
#                         }
#                     ]
#                 }
#             }
            
#             response = requests.post(url, headers=headers, json=payload)
            
#             if response.status_code in [200, 201]:
#                 return True, f"Successfully uploaded: {filename}"
#             elif response.status_code == 403:
#                 return False, f"403 Error - Your API key doesn't have INDEX permission. Check API key settings in Vectara Console."
#             else:
#                 return False, f"Upload failed ({response.status_code}): {response.text}"
                
#         except Exception as e:
#             return False, f"Error uploading {filename}: {str(e)}"
    
#     def check_permissions(self):
#         """Check what permissions this API key has"""
#         try:
#             # Try to list documents (requires READ permission)
#             read_test = self.list_documents()
#             can_read = read_test[1] is None
            
#             # Check corpus info
#             url = f"{self.base_url}/corpora/{self.corpus_id}"
#             response = requests.get(url, headers=self.headers)
#             can_view_corpus = response.status_code == 200
            
#             return {
#                 "can_read": can_read,
#                 "can_view_corpus": can_view_corpus,
#                 "read_error": read_test[1] if not can_read else None
#             }
#         except Exception as e:
#             return {"error": str(e)}
    
#     def query(self, query_text, num_results=10):
#         """Query the Vectara corpus"""
#         try:
#             url = f"{self.base_url}/query"
            
#             payload = {
#                 "query": query_text,
#                 "search": {
#                     "corpora": [
#                         {
#                             "corpus_key": self.corpus_id,
#                             "limit": num_results
#                         }
#                     ],
#                     "limit": num_results
#                 },
#                 "generation": {
#                     "generation_preset_name": "vectara-summary-ext-v1.2.0",
#                     "max_used_search_results": 5
#                 }
#             }
            
#             response = requests.post(url, headers=self.headers, json=payload)
            
#             if response.status_code == 200:
#                 return response.json(), None
#             elif response.status_code == 403:
#                 return None, f"403 Forbidden - Check query permissions: {response.text}"
#             else:
#                 return None, f"Query failed ({response.status_code}): {response.text}"
                
#         except Exception as e:
#             return None, f"Error querying: {str(e)}"
    
#     def list_documents(self):
#         """List all documents in the corpus"""
#         try:
#             url = f"{self.base_url}/corpora/{self.corpus_id}/documents"
#             response = requests.get(url, headers=self.headers)
            
#             if response.status_code == 200:
#                 return response.json(), None
#             else:
#                 return None, f"Failed to list documents ({response.status_code}): {response.text}"
                
#         except Exception as e:
#             return None, f"Error listing documents: {str(e)}"

# def initialize_vectara(api_key, customer_id, corpus_id):
#     """Initialize Vectara client with credentials"""
#     try:
#         client = VectaraClient(api_key, customer_id, corpus_id)
#         # Test the connection
#         success, message = client.test_connection()
#         if success:
#             return client, None
#         else:
#             return None, message
#     except Exception as e:
#         return None, str(e)

# def extract_metrics_from_response(response_data, metric_names=None):
#     """Extract financial metrics from Vectara response"""
#     if metric_names is None:
#         metric_names = ["Revenue", "Net Profit", "Gross Profit", "Total Assets", "Total Liabilities"]
    
#     metrics = {name: "N/A" for name in metric_names}
    
#     if response_data and 'search_results' in response_data:
#         combined_text = ""
#         for result in response_data['search_results'][:5]:
#             if 'text' in result:
#                 combined_text += " " + result['text']
        
#         for metric in metric_names:
#             # Try different patterns
#             patterns = [
#                 rf"{metric}\s*[:\-]?\s*\$?\s*(\d{{1,3}}(?:,\d{{3}})*(?:\.\d{{2}})?)",
#                 rf"{metric}\s*\(?\$?(\d{{1,3}}(?:,\d{{3}})*(?:\.\d{{2}})?)\)?",
#             ]
            
#             for pattern in patterns:
#                 match = re.search(pattern, combined_text, re.IGNORECASE)
#                 if match:
#                     metrics[metric] = match.group(1).replace(",", "")
#                     break
    
#     return metrics

# # Main App Layout
# st.title("📊 Vectara Financial Analysis Dashboard")
# st.markdown("Upload financial documents, query them intelligently, and compare metrics across multiple files.")

# # Sidebar for configuration
# with st.sidebar:
#     st.header("⚙️ Configuration")
    
#     # Troubleshooting tips
#     with st.expander("❓ Troubleshooting 403 Errors"):
#         st.markdown("""
#         **Common causes of 403 Forbidden errors:**
        
#         1. **Wrong API Key Type**: Make sure you're using a **Personal API Key**, not OAuth credentials
#         2. **Missing INDEX Permission**: Your API key needs **INDEX** permission to upload documents
#         3. **Incorrect Corpus ID**: Verify the corpus ID exists and you have access
#         4. **Wrong Customer ID**: Double-check your customer ID matches your account
        
#         **How to fix:**
#         1. Go to Vectara Console → Authorization → API Keys
#         2. Either edit existing key OR create new one
#         3. **IMPORTANT**: Check the "Index" checkbox under permissions
#         4. Make sure the corpus "hello_world" is selected in the key's access list
#         5. Copy the new API key and reconnect
        
#         **Required Permissions for this app:**
#         - ✅ **Query** - To search documents
#         - ✅ **Index** - To upload documents (THIS IS REQUIRED!)
#         - ✅ **Read** - To list documents
        
#         **API Key Format**: Should look like `zut_xxxxx...` or `zwt_xxxxx...`
#         """)
    
#     st.divider()
    
#     # Permission checker
#     if st.session_state.connected and st.session_state.vectara_client:
#         with st.expander("🔍 Check API Key Permissions"):
#             if st.button("Test Permissions"):
#                 with st.spinner("Checking permissions..."):
#                     perms = st.session_state.vectara_client.check_permissions()
                    
#                     st.write("**Permission Test Results:**")
#                     if "error" in perms:
#                         st.error(f"Error: {perms['error']}")
#                     else:
#                         st.write(f"✅ Can view corpus: {perms['can_view_corpus']}")
#                         st.write(f"✅ Can read/list documents: {perms['can_read']}")
                        
#                         if not perms['can_read']:
#                             st.error(f"Read error: {perms['read_error']}")
                        
#                         st.warning("⚠️ Cannot test INDEX permission without uploading. If uploads fail with 403, your key is missing INDEX permission.")
    
#     st.divider()
    
#     # Connection inputs
#     api_key = st.text_input("Vectara API Key", type="password", help="Your Personal API Key (starts with zut_ or zwt_)", key="api_key_input")
#     customer_id = st.text_input("Customer ID", help="Your Vectara Customer ID", key="customer_id_input")
#     corpus_id = st.text_input("Corpus ID", help="Your Vectara Corpus ID or Key", key="corpus_id_input")
    
#     if st.button("Connect to Vectara", type="primary"):
#         if api_key and customer_id and corpus_id:
#             with st.spinner("Testing connection..."):
#                 client, error = initialize_vectara(api_key, customer_id, corpus_id)
#                 if client:
#                     st.session_state.vectara_client = client
#                     st.session_state.connected = True
#                     st.success("✅ Connected successfully!")
#                     st.rerun()
#                 else:
#                     st.error(f"❌ Connection failed: {error}")
#                     st.info("Please check the troubleshooting guide above")
#         else:
#             st.warning("Please fill in all fields")
    
#     st.divider()
    
#     # Display connection status
#     if st.session_state.connected and st.session_state.vectara_client:
#         st.success("🟢 Connected")
        
#         # List documents in corpus
#         if st.button("🔍 View Corpus Documents"):
#             with st.spinner("Loading documents..."):
#                 docs, error = st.session_state.vectara_client.list_documents()
#                 if error:
#                     st.error(f"Error: {error}")
#                 elif docs and 'documents' in docs:
#                     st.write(f"**Documents in corpus:** {len(docs['documents'])}")
#                     for i, doc in enumerate(docs['documents'][:10], 1):
#                         doc_id = doc.get('id', 'N/A')
#                         st.text(f"{i}. ID: {doc_id}")
#                 else:
#                     st.info("No documents found")
        
#         # Disconnect button
#         if st.button("Disconnect", type="secondary"):
#             st.session_state.vectara_client = None
#             st.session_state.connected = False
#             st.rerun()
#     else:
#         st.warning("🔴 Not Connected")

# # Main content area with tabs
# tab1, tab2, tab3 = st.tabs(["📤 Upload Files", "💬 Query Documents", "📈 Financial Comparison"])

# # Tab 1: Upload Files
# with tab1:
#     st.header("Upload PDF Documents")
    
#     if not st.session_state.connected:
#         st.warning("⚠️ Please connect to Vectara first using the sidebar.")
#     else:
#         # Upload method selector
#         upload_method = st.radio(
#             "Select upload method:",
#             ["V2 API (Recommended)", "V1 API (Alternative)"],
#             help="Try V1 API if V2 gives 403 errors"
#         )
        
#         uploaded_files = st.file_uploader(
#             "Choose PDF files",
#             type=['pdf'],
#             accept_multiple_files=True,
#             help="Upload one or more PDF files to analyze",
#             key="pdf_uploader"
#         )
        
#         if uploaded_files and st.button("📤 Upload to Vectara", type="primary", key="upload_btn"):
#             progress_bar = st.progress(0)
#             status_text = st.empty()
            
#             success_count = 0
#             total_files = len(uploaded_files)
            
#             client = st.session_state.vectara_client
            
#             for i, file in enumerate(uploaded_files):
#                 status_text.text(f"Uploading {file.name}...")
                
#                 # Read file content
#                 file_content = file.read()
                
#                 # Choose upload method
#                 if upload_method == "V1 API (Alternative)":
#                     success, message = client.upload_file_v1(file_content, file.name)
#                 else:
#                     success, message = client.upload_file(file_content, file.name)
                
#                 if success:
#                     st.success(message)
#                     success_count += 1
#                     if file.name not in st.session_state.uploaded_files_list:
#                         st.session_state.uploaded_files_list.append(file.name)
#                 else:
#                     st.error(message)
                
#                 progress_bar.progress((i + 1) / total_files)
            
#             status_text.text(f"Upload complete! {success_count}/{total_files} files uploaded successfully.")
        
#         # Display uploaded files
#         if st.session_state.uploaded_files_list:
#             st.subheader("📋 Uploaded Files")
#             for i, filename in enumerate(st.session_state.uploaded_files_list, 1):
#                 st.text(f"{i}. {filename}")

# # Tab 2: Query Documents
# with tab2:
#     st.header("Ask Questions About Your Documents")
    
#     if not st.session_state.connected:
#         st.warning("⚠️ Please connect to Vectara first using the sidebar.")
#     else:
#         # Query input
#         query_input = st.text_area(
#             "Enter your question:",
#             placeholder="e.g., What is the total revenue in FY2024?",
#             height=100,
#             key="query_input"
#         )
        
#         col1, col2 = st.columns([1, 5])
#         with col1:
#             query_button = st.button("🔍 Search", type="primary", key="search_btn")
#         with col2:
#             if st.button("🗑️ Clear History", key="clear_btn"):
#                 st.session_state.chat_history = []
#                 st.rerun()
        
#         if query_button and query_input:
#             with st.spinner("Searching..."):
#                 client = st.session_state.vectara_client
#                 response, error = client.query(query_input)
                
#                 if error:
#                     st.error(f"Query error: {error}")
#                 else:
#                     # Add to chat history
#                     st.session_state.chat_history.append({
#                         'timestamp': datetime.now().strftime("%H:%M:%S"),
#                         'query': query_input,
#                         'response': response
#                     })
#                     st.rerun()
        
#         # Display chat history
#         if st.session_state.chat_history:
#             st.divider()
#             st.subheader("💬 Conversation History")
            
#             for i, chat in enumerate(reversed(st.session_state.chat_history)):
#                 with st.container():
#                     st.markdown(f"**🕐 {chat['timestamp']}**")
#                     st.markdown(f"**Q:** {chat['query']}")
                    
#                     # Display generated summary
#                     if 'summary' in chat['response']:
#                         st.markdown(f"**A:** {chat['response']['summary']}")
                    
#                     # Display search results
#                     if 'search_results' in chat['response']:
#                         with st.expander("📄 View Source Snippets"):
#                             for j, result in enumerate(chat['response']['search_results'][:3], 1):
#                                 score = result.get('score', 0)
#                                 text = result.get('text', 'N/A')
#                                 st.markdown(f"**Source {j}** (Score: {score:.3f})")
#                                 st.text(text[:300] + "..." if len(text) > 300 else text)
#                                 st.markdown("---")
                    
#                     st.divider()

# # Tab 3: Financial Comparison
# with tab3:
#     st.header("Compare Financial Metrics Across Documents")
    
#     if not st.session_state.connected:
#         st.warning("⚠️ Please connect to Vectara first using the sidebar.")
#     else:
#         st.markdown("**Select metrics to compare:**")
        
#         # Metrics to extract
#         default_metrics = ["Revenue", "Net Profit", "Gross Profit", "Total Assets"]
#         custom_metrics = st.text_input(
#             "Additional metrics (comma-separated):",
#             placeholder="e.g., Operating Expenses, Cash Flow",
#             key="custom_metrics_input"
#         )
        
#         all_metrics = default_metrics.copy()
#         if custom_metrics:
#             all_metrics.extend([m.strip() for m in custom_metrics.split(',')])
        
#         # Query for each metric
#         if st.button("📊 Generate Comparison", type="primary", key="comparison_btn"):
#             with st.spinner("Extracting financial metrics..."):
#                 client = st.session_state.vectara_client
#                 comparison_data = {}
                
#                 # Query for all metrics at once
#                 query_text = f"financial statements showing: {', '.join(all_metrics)}"
#                 response, error = client.query(query_text, num_results=10)
                
#                 if not error and response:
#                     metrics = extract_metrics_from_response(response, all_metrics)
#                     comparison_data['Document Analysis'] = metrics
                    
#                     # Create comparison DataFrame
#                     if comparison_data:
#                         df = pd.DataFrame(comparison_data)
#                         df.index.name = 'Metric'
                        
#                         st.subheader("📋 Metrics Summary")
#                         st.dataframe(df, use_container_width=True)
                        
#                         # Convert to numeric for visualization
#                         df_numeric = df.copy()
#                         for col in df_numeric.columns:
#                             df_numeric[col] = pd.to_numeric(df_numeric[col], errors='coerce')
                        
#                         # Chart visualization
#                         st.subheader("📊 Visual Comparison")
#                         chart_metric = st.selectbox("Select metric to visualize:", all_metrics, key="chart_metric_select")
                        
#                         if chart_metric in df_numeric.index:
#                             chart_data = df_numeric.loc[chart_metric].dropna()
#                             if not chart_data.empty:
#                                 st.bar_chart(chart_data)
#                             else:
#                                 st.info("No numeric data available for this metric.")
                        
#                         # Download option
#                         csv = df.to_csv()
#                         st.download_button(
#                             label="📥 Download Comparison as CSV",
#                             data=csv,
#                             file_name="financial_comparison.csv",
#                             mime="text/csv",
#                             key="download_csv_btn"
#                         )
#                 else:
#                     st.error(f"Error extracting metrics: {error}")

# # Footer
# st.divider()
# st.markdown("""
# <div style='text-align: center; color: gray; font-size: 0.9em;'>
#     <p>Vectara Financial Analysis Dashboard | Powered by Vectara RAG</p>
# </div>
# """, unsafe_allow_html=True)

# import streamlit as st
# import requests
# import json
# import base64
# import re
# import pandas as pd
# from datetime import datetime
# import os

# # Page configuration
# st.set_page_config(
#     page_title="Vectara Financial Analysis",
#     page_icon="📊",
#     layout="wide"
# )

# # Initialize session state
# if 'vectara_client' not in st.session_state:
#     st.session_state.vectara_client = None
# if 'uploaded_files_list' not in st.session_state:
#     st.session_state.uploaded_files_list = []
# if 'chat_history' not in st.session_state:
#     st.session_state.chat_history = []
# if 'connected' not in st.session_state:
#     st.session_state.connected = False

# # Helper Functions
# class VectaraClient:
#     """Custom Vectara client using REST API"""
    
#     def __init__(self, api_key, customer_id, corpus_id):
#         self.api_key = api_key
#         self.customer_id = customer_id
#         self.corpus_id = corpus_id
#         self.base_url = "https://api.vectara.io/v2"
#         self.headers = {
#             "x-api-key": api_key,
#             "Content-Type": "application/json",
#             "customer-id": customer_id
#         }
    
#     def test_connection(self):
#         """Test the connection to Vectara"""
#         try:
#             url = f"{self.base_url}/corpora/{self.corpus_id}"
#             response = requests.get(url, headers=self.headers)
            
#             if response.status_code == 200:
#                 return True, "Connection successful!"
#             elif response.status_code == 403:
#                 return False, "403 Forbidden - Check your API key and permissions"
#             elif response.status_code == 401:
#                 return False, "401 Unauthorized - Invalid API key"
#             elif response.status_code == 404:
#                 return False, "404 Not Found - Invalid Corpus ID"
#             else:
#                 return False, f"Error {response.status_code}: {response.text}"
#         except Exception as e:
#             return False, f"Connection error: {str(e)}"
    
#     def upload_file(self, file_content, filename):
#         """Upload a file to Vectara corpus using multipart/form-data"""
#         try:
#             # Use the file upload endpoint with multipart
#             url = f"{self.base_url}/corpora/{self.corpus_id}/upload_file"
            
#             # Prepare headers for file upload (remove Content-Type, let requests set it)
#             headers = {
#                 "x-api-key": self.api_key,
#                 "customer-id": self.customer_id
#             }
            
#             # Prepare the file
#             files = {
#                 'file': (filename, file_content, 'application/pdf')
#             }
            
#             # Additional metadata
#             data = {
#                 'metadata': json.dumps({
#                     'filename': filename,
#                     'upload_date': datetime.now().isoformat()
#                 })
#             }
            
#             response = requests.post(url, headers=headers, files=files, data=data)
            
#             if response.status_code in [200, 201]:
#                 return True, f"Successfully uploaded: {filename}"
#             elif response.status_code == 403:
#                 return False, f"403 Forbidden - Check corpus permissions for uploads. Response: {response.text}"
#             elif response.status_code == 401:
#                 return False, f"401 Unauthorized - Invalid API key. Response: {response.text}"
#             else:
#                 return False, f"Upload failed ({response.status_code}): {response.text}"
                
#         except Exception as e:
#             return False, f"Error uploading {filename}: {str(e)}"
    
#     def upload_file_v1(self, file_content, filename):
#         """Alternative upload method using v1 API"""
#         try:
#             url = f"https://api.vectara.io/v1/upload"
            
#             headers = {
#                 "x-api-key": self.api_key,
#                 "customer-id": self.customer_id
#             }
            
#             files = {
#                 'file': (filename, file_content, 'application/pdf')
#             }
            
#             data = {
#                 'c': self.customer_id,
#                 'o': self.corpus_id
#             }
            
#             response = requests.post(url, headers=headers, files=files, data=data)
            
#             if response.status_code in [200, 201]:
#                 return True, f"Successfully uploaded: {filename}"
#             else:
#                 return False, f"Upload failed ({response.status_code}): {response.text}"
                
#         except Exception as e:
#             return False, f"Error uploading {filename}: {str(e)}"
    
#     def query(self, query_text, num_results=10):
#         """Query the Vectara corpus"""
#         try:
#             url = f"{self.base_url}/query"
            
#             payload = {
#                 "query": query_text,
#                 "search": {
#                     "corpora": [
#                         {
#                             "corpus_key": self.corpus_id,
#                             "limit": num_results
#                         }
#                     ],
#                     "limit": num_results
#                 },
#                 "generation": {
#                     "generation_preset_name": "vectara-summary-ext-v1.2.0",
#                     "max_used_search_results": 5
#                 }
#             }
            
#             response = requests.post(url, headers=self.headers, json=payload)
            
#             if response.status_code == 200:
#                 return response.json(), None
#             elif response.status_code == 403:
#                 return None, f"403 Forbidden - Check query permissions: {response.text}"
#             else:
#                 return None, f"Query failed ({response.status_code}): {response.text}"
                
#         except Exception as e:
#             return None, f"Error querying: {str(e)}"
    
#     def list_documents(self):
#         """List all documents in the corpus"""
#         try:
#             url = f"{self.base_url}/corpora/{self.corpus_id}/documents"
#             response = requests.get(url, headers=self.headers)
            
#             if response.status_code == 200:
#                 return response.json(), None
#             else:
#                 return None, f"Failed to list documents ({response.status_code}): {response.text}"
                
#         except Exception as e:
#             return None, f"Error listing documents: {str(e)}"

# def initialize_vectara(api_key, customer_id, corpus_id):
#     """Initialize Vectara client with credentials"""
#     try:
#         client = VectaraClient(api_key, customer_id, corpus_id)
#         # Test the connection
#         success, message = client.test_connection()
#         if success:
#             return client, None
#         else:
#             return None, message
#     except Exception as e:
#         return None, str(e)

# def extract_metrics_from_response(response_data, metric_names=None):
#     """Extract financial metrics from Vectara response"""
#     if metric_names is None:
#         metric_names = ["Revenue", "Net Profit", "Gross Profit", "Total Assets", "Total Liabilities"]
    
#     metrics = {name: "N/A" for name in metric_names}
    
#     if response_data and 'search_results' in response_data:
#         combined_text = ""
#         for result in response_data['search_results'][:5]:
#             if 'text' in result:
#                 combined_text += " " + result['text']
        
#         for metric in metric_names:
#             # Try different patterns
#             patterns = [
#                 rf"{metric}\s*[:\-]?\s*\$?\s*(\d{{1,3}}(?:,\d{{3}})*(?:\.\d{{2}})?)",
#                 rf"{metric}\s*\(?\$?(\d{{1,3}}(?:,\d{{3}})*(?:\.\d{{2}})?)\)?",
#             ]
            
#             for pattern in patterns:
#                 match = re.search(pattern, combined_text, re.IGNORECASE)
#                 if match:
#                     metrics[metric] = match.group(1).replace(",", "")
#                     break
    
#     return metrics

# # Main App Layout
# st.title("📊 Vectara Financial Analysis Dashboard")
# st.markdown("Upload financial documents, query them intelligently, and compare metrics across multiple files.")

# # Sidebar for configuration
# with st.sidebar:
#     st.header("⚙️ Configuration")
    
#     # Troubleshooting tips
#     with st.expander("❓ Troubleshooting 403 Errors"):
#         st.markdown("""
#         **Common causes of 403 Forbidden errors:**
        
#         1. **Wrong API Key Type**: Make sure you're using a **Personal API Key**, not OAuth credentials
#         2. **Incorrect Corpus ID**: Verify the corpus ID exists and you have access
#         3. **Missing Permissions**: Ensure your API key has read/write access to the corpus
#         4. **Wrong Customer ID**: Double-check your customer ID matches your account
        
#         **How to get credentials:**
#         1. Go to Vectara Console
#         2. Navigate to Authorization → API Keys
#         3. Create a new Personal API Key with corpus access
#         4. Copy the API Key, Customer ID, and Corpus ID
        
#         **API Key Format**: Should look like `zut_xxxxx...` or `zwt_xxxxx...`
#         """)
    
#     st.divider()
    
#     # Connection inputs
#     api_key = st.text_input("Vectara API Key", type="password", help="Your Personal API Key (starts with zut_ or zwt_)", key="api_key_input")
#     customer_id = st.text_input("Customer ID", help="Your Vectara Customer ID", key="customer_id_input")
#     corpus_id = st.text_input("Corpus ID", help="Your Vectara Corpus ID or Key", key="corpus_id_input")
    
#     if st.button("Connect to Vectara", type="primary"):
#         if api_key and customer_id and corpus_id:
#             with st.spinner("Testing connection..."):
#                 client, error = initialize_vectara(api_key, customer_id, corpus_id)
#                 if client:
#                     st.session_state.vectara_client = client
#                     st.session_state.connected = True
#                     st.success("✅ Connected successfully!")
#                     st.rerun()
#                 else:
#                     st.error(f"❌ Connection failed: {error}")
#                     st.info("Please check the troubleshooting guide above")
#         else:
#             st.warning("Please fill in all fields")
    
#     st.divider()
    
#     # Display connection status
#     if st.session_state.connected and st.session_state.vectara_client:
#         st.success("🟢 Connected")
        
#         # List documents in corpus
#         if st.button("🔍 View Corpus Documents"):
#             with st.spinner("Loading documents..."):
#                 docs, error = st.session_state.vectara_client.list_documents()
#                 if error:
#                     st.error(f"Error: {error}")
#                 elif docs and 'documents' in docs:
#                     st.write(f"**Documents in corpus:** {len(docs['documents'])}")
#                     for i, doc in enumerate(docs['documents'][:10], 1):
#                         doc_id = doc.get('id', 'N/A')
#                         st.text(f"{i}. ID: {doc_id}")
#                 else:
#                     st.info("No documents found")
        
#         # Disconnect button
#         if st.button("Disconnect", type="secondary"):
#             st.session_state.vectara_client = None
#             st.session_state.connected = False
#             st.rerun()
#     else:
#         st.warning("🔴 Not Connected")

# # Main content area with tabs
# tab1, tab2, tab3 = st.tabs(["📤 Upload Files", "💬 Query Documents", "📈 Financial Comparison"])

# # Tab 1: Upload Files
# with tab1:
#     st.header("Upload PDF Documents")
    
#     if not st.session_state.connected:
#         st.warning("⚠️ Please connect to Vectara first using the sidebar.")
#     else:
#         # Upload method selector
#         upload_method = st.radio(
#             "Select upload method:",
#             ["V2 API (Recommended)", "V1 API (Alternative)"],
#             help="Try V1 API if V2 gives 403 errors"
#         )
        
#         uploaded_files = st.file_uploader(
#             "Choose PDF files",
#             type=['pdf'],
#             accept_multiple_files=True,
#             help="Upload one or more PDF files to analyze",
#             key="pdf_uploader"
#         )
        
#         if uploaded_files and st.button("📤 Upload to Vectara", type="primary", key="upload_btn"):
#             progress_bar = st.progress(0)
#             status_text = st.empty()
            
#             success_count = 0
#             total_files = len(uploaded_files)
            
#             client = st.session_state.vectara_client
            
#             for i, file in enumerate(uploaded_files):
#                 status_text.text(f"Uploading {file.name}...")
                
#                 # Read file content
#                 file_content = file.read()
                
#                 # Choose upload method
#                 if upload_method == "V1 API (Alternative)":
#                     success, message = client.upload_file_v1(file_content, file.name)
#                 else:
#                     success, message = client.upload_file(file_content, file.name)
                
#                 if success:
#                     st.success(message)
#                     success_count += 1
#                     if file.name not in st.session_state.uploaded_files_list:
#                         st.session_state.uploaded_files_list.append(file.name)
#                 else:
#                     st.error(message)
                
#                 progress_bar.progress((i + 1) / total_files)
            
#             status_text.text(f"Upload complete! {success_count}/{total_files} files uploaded successfully.")
        
#         # Display uploaded files
#         if st.session_state.uploaded_files_list:
#             st.subheader("📋 Uploaded Files")
#             for i, filename in enumerate(st.session_state.uploaded_files_list, 1):
#                 st.text(f"{i}. {filename}")

# # Tab 2: Query Documents
# with tab2:
#     st.header("Ask Questions About Your Documents")
    
#     if not st.session_state.connected:
#         st.warning("⚠️ Please connect to Vectara first using the sidebar.")
#     else:
#         # Query input
#         query_input = st.text_area(
#             "Enter your question:",
#             placeholder="e.g., What is the total revenue in FY2024?",
#             height=100,
#             key="query_input"
#         )
        
#         col1, col2 = st.columns([1, 5])
#         with col1:
#             query_button = st.button("🔍 Search", type="primary", key="search_btn")
#         with col2:
#             if st.button("🗑️ Clear History", key="clear_btn"):
#                 st.session_state.chat_history = []
#                 st.rerun()
        
#         if query_button and query_input:
#             with st.spinner("Searching..."):
#                 client = st.session_state.vectara_client
#                 response, error = client.query(query_input)
                
#                 if error:
#                     st.error(f"Query error: {error}")
#                 else:
#                     # Add to chat history
#                     st.session_state.chat_history.append({
#                         'timestamp': datetime.now().strftime("%H:%M:%S"),
#                         'query': query_input,
#                         'response': response
#                     })
#                     st.rerun()
        
#         # Display chat history
#         if st.session_state.chat_history:
#             st.divider()
#             st.subheader("💬 Conversation History")
            
#             for i, chat in enumerate(reversed(st.session_state.chat_history)):
#                 with st.container():
#                     st.markdown(f"**🕐 {chat['timestamp']}**")
#                     st.markdown(f"**Q:** {chat['query']}")
                    
#                     # Display generated summary
#                     if 'summary' in chat['response']:
#                         st.markdown(f"**A:** {chat['response']['summary']}")
                    
#                     # Display search results
#                     if 'search_results' in chat['response']:
#                         with st.expander("📄 View Source Snippets"):
#                             for j, result in enumerate(chat['response']['search_results'][:3], 1):
#                                 score = result.get('score', 0)
#                                 text = result.get('text', 'N/A')
#                                 st.markdown(f"**Source {j}** (Score: {score:.3f})")
#                                 st.text(text[:300] + "..." if len(text) > 300 else text)
#                                 st.markdown("---")
                    
#                     st.divider()

# # Tab 3: Financial Comparison
# with tab3:
#     st.header("Compare Financial Metrics Across Documents")
    
#     if not st.session_state.connected:
#         st.warning("⚠️ Please connect to Vectara first using the sidebar.")
#     else:
#         st.markdown("**Select metrics to compare:**")
        
#         # Metrics to extract
#         default_metrics = ["Revenue", "Net Profit", "Gross Profit", "Total Assets"]
#         custom_metrics = st.text_input(
#             "Additional metrics (comma-separated):",
#             placeholder="e.g., Operating Expenses, Cash Flow",
#             key="custom_metrics_input"
#         )
        
#         all_metrics = default_metrics.copy()
#         if custom_metrics:
#             all_metrics.extend([m.strip() for m in custom_metrics.split(',')])
        
#         # Query for each metric
#         if st.button("📊 Generate Comparison", type="primary", key="comparison_btn"):
#             with st.spinner("Extracting financial metrics..."):
#                 client = st.session_state.vectara_client
#                 comparison_data = {}
                
#                 # Query for all metrics at once
#                 query_text = f"financial statements showing: {', '.join(all_metrics)}"
#                 response, error = client.query(query_text, num_results=10)
                
#                 if not error and response:
#                     metrics = extract_metrics_from_response(response, all_metrics)
#                     comparison_data['Document Analysis'] = metrics
                    
#                     # Create comparison DataFrame
#                     if comparison_data:
#                         df = pd.DataFrame(comparison_data)
#                         df.index.name = 'Metric'
                        
#                         st.subheader("📋 Metrics Summary")
#                         st.dataframe(df, use_container_width=True)
                        
#                         # Convert to numeric for visualization
#                         df_numeric = df.copy()
#                         for col in df_numeric.columns:
#                             df_numeric[col] = pd.to_numeric(df_numeric[col], errors='coerce')
                        
#                         # Chart visualization
#                         st.subheader("📊 Visual Comparison")
#                         chart_metric = st.selectbox("Select metric to visualize:", all_metrics, key="chart_metric_select")
                        
#                         if chart_metric in df_numeric.index:
#                             chart_data = df_numeric.loc[chart_metric].dropna()
#                             if not chart_data.empty:
#                                 st.bar_chart(chart_data)
#                             else:
#                                 st.info("No numeric data available for this metric.")
                        
#                         # Download option
#                         csv = df.to_csv()
#                         st.download_button(
#                             label="📥 Download Comparison as CSV",
#                             data=csv,
#                             file_name="financial_comparison.csv",
#                             mime="text/csv",
#                             key="download_csv_btn"
#                         )
#                 else:
#                     st.error(f"Error extracting metrics: {error}")

# # Footer
# st.divider()
# st.markdown("""
# <div style='text-align: center; color: gray; font-size: 0.9em;'>
#     <p>Vectara Financial Analysis Dashboard | Powered by Vectara RAG</p>
# </div>
# """, unsafe_allow_html=True)
