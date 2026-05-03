from flask import Flask, request, jsonify
import psycopg2

app = Flask(__name__)

@app.route('/', methods=['GET'])
def home():
    return "Server is alive", 200

def get_connection():
    return psycopg2.connect(
        host="ep-morning-fog-a4uzpxwr.us-east-1.aws.neon.tech",
        database="neondb",
        user="neondb_owner",
        password="npg_tTQ2cyP5SluG",
        port="5432",
        sslmode="require"
    )

@app.route('/api/iot', methods=['POST'])
def receive_data():
    try:
        data = request.json
        print("Incoming:", data)

        # Existing fields
        email = data.get("email")
        moisture = int(data.get("moisture"))
        ph = float(data.get("ph"))
        temperature = int(data.get("temperature"))

        # ✅ New fields
        ec = int(data.get("ec"))
        nitrogen = int(data.get("nitrogen"))
        phosphorus = int(data.get("phosphorus"))
        potassium = int(data.get("potassium"))

        conn = get_connection()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO sensor_data 
            (email, moisture, ph, temperature, ec, nitrogen, phosphorus, potassium)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (email, moisture, ph, temperature, ec, nitrogen, phosphorus, potassium))

        conn.commit()

        cur.close()
        conn.close()

        return jsonify({"status": "success"})

    except Exception as e:
        print("🔥 ERROR:", e)
        return jsonify({"status": "error"}), 200
        

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)