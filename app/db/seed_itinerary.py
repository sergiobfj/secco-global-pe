"""Informações fornecidas pela equipe, sem horários ou confirmações presumidas."""
from app.db.connection import connect

TOURISM = ("Obelisco","Plaza de Mayo","Casa Rosada","Puerto Madero","Recoleta","Palermo",
           "San Telmo","Caminito","Tigre e Delta do Paraná","Reserva Ecológica Costanera Sur")


def seed_itinerary(database_path):
    with connect(database_path) as db:
        ids = {row["codigo"]:row["id"] for row in db.execute("SELECT id,codigo FROM missions")}
        records = []
        for day in ("18","19"):
            records.append(("argentina",f"simposio-{day}",
                "1º Simpósio Iberoamericano de Inovação, Ciência e Tecnologia",
                "evento","a_confirmar",None,f"2026-11-{day}","Palacio Paz",
                "Av. Santa Fe 750, Buenos Aires",1,
                "Datas e endereço previstos informados pela equipe. Horários e inscrição não confirmados. Origem documental a validar."))
        for index,name in enumerate(("SECOM / Embaixada do Brasil","InvestBA","Parque de Innovación")):
            records.append(("argentina",f"institucional-{index}",name,"institucional","a_confirmar",
                            None,None,"","",0,"Oportunidade de agenda informada pela equipe. Sem reunião, data ou horário confirmados."))
        for index,name in enumerate(TOURISM):
            records.append(("argentina",f"turismo-{index}",name,"turismo","sugestao",
                            "sugestao_viajantes",None,name,"",0,"Sugestão turística. Sem reserva ou programação confirmada."))
        for index,name in enumerate(("Bootcamp na NOVA SBE","Web Summit","Aveiro Tech Week","Portus Park","UPTEC")):
            records.append(("portugal",f"prevista-{index}",name,"evento" if index<3 else "institucional",
                            "a_confirmar",None,None,"","",0,"Atividade prevista informada pela equipe. Data, horário, endereço e origem documental a validar."))
        for country,key,title,category,status,origin,day,place,address,checked,notes in records:
            db.execute("""INSERT INTO itinerary_items(mission_id,seed_key,titulo,categoria,status,origem,data,
                local,endereco,endereco_validado,observacoes)
                VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(seed_key) DO NOTHING""",
                       (ids[country],country+":"+key,title,category,status,origin,day,place,address,checked,notes))
