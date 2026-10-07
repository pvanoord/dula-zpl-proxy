#!/usr/bin/env python3

import argparse
import datetime
import re
import socket
import threading


LISTEN_IP = "0.0.0.0"
LISTEN_PORT = 9100

PRINTER_IP = "172.31.254.247"
PRINTER_PORT = 9100

TEST_ORIGINAL_FILE = "/tmp/dula-test-original.zpl"
TEST_MODIFIED_FILE = "/tmp/dula-test-output.zpl"


# Normale, niet-geroteerde Zebra Font 0-correcties.
#
# Formaat:
# oorspronkelijke hoogte: (nieuwe hoogte, nieuwe breedte)
FONT_MAP_NORMAL = {
    68: (68, 20),
    48: (48, 14),
    41: (41, 12),
    33: (33, 10),
    28: (28, 9),
    24: (24, 8),
    21: (21, 7),
    20: (20, 7),
    19: (19, 6),
    18: (18, 6),
    16: (16, 8),
}


# Gerichte positiecorrecties voor het DPD-label.
#
# Deze correcties worden pas na de fontcorrecties uitgevoerd.
POSITION_REPLACEMENTS = {
    # Contactpersoon verder naar rechts.
    "^FO87,420": "^FO125,420",

    # Consignmentnummer iets omhoog en minder ver naar rechts.
    "^FO15,542": "^FO15,534",
    "^FO119,542": "^FO155,534",
    # De drie onderdelen van de regel boven DE-DPD-0145.
    # Ze worden dichter bij elkaar gezet en op dezelfde baseline geplaatst.
    "^FO23,732": "^FO23,733",
    "^FO111,733": "^FO115,733",
    "^FO303,740": "^FO290,733",
}


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="ZPL-proxy voor de DULA 222"
    )

    parser.add_argument(
        "--test",
        action="store_true",
        help=(
            "Toon en bewaar de aangepaste ZPL, "
            "maar stuur niets naar de printer."
        )
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help=(
            "Bewaar van iedere printjob de originele "
            "en aangepaste ZPL met een tijdstempel."
        )
    )

    return parser.parse_args()


def replace_normal_font(match):
    """
    Corrigeert Zebra Font 0 uitsluitend binnen normale ^FWN-secties.
    """

    original_height = int(match.group(1))

    if original_height in FONT_MAP_NORMAL:
        new_height, new_width = FONT_MAP_NORMAL[original_height]
    else:
        new_height = original_height
        new_width = max(int(original_height * 0.30), 1)

    replacement = f"^A0N,{new_height},{new_width}"

    print(
        f"NORMAL font aangepast: "
        f"^A0,,{original_height} -> {replacement}"
    )

    return replacement


def adjust_fonts_by_orientation(text):
    """
    Verwerkt de ZPL per ^FWN- en ^FWR-sectie.

    Binnen ^FWN:
      - ^A0,,hoogte wordt vervangen door ^A0N,hoogte,breedte.

    Binnen ^FWR:
      - de volledige inhoud blijft exact ongewijzigd;
      - ook de oorspronkelijke ^A0,,hoogte blijft behouden.

    Hierdoor blijven de twee rechterblokken verticaal en behoudt de
    DULA de originele DPD-opbouw voor deze velden.
    """

    parts = re.split(
        r"(\^FWN|\^FWR)",
        text
    )

    current_orientation = "N"
    output = []

    for part in parts:
        if part == "^FWN":
            current_orientation = "N"
            output.append(part)
            continue

        if part == "^FWR":
            current_orientation = "R"
            output.append(part)
            continue

        if current_orientation == "R":
            # FWR-blokken volledig ongemoeid laten.
            output.append(part)
            continue

        modified_part = re.sub(
            r"\^A0,,(\d+)",
            replace_normal_font,
            part
        )

        output.append(modified_part)

    return "".join(output)


def apply_position_corrections(text):
    """
    Past de specifieke DPD-veldposities aan.
    """

    for original, replacement in POSITION_REPLACEMENTS.items():
        if original in text:
            print(
                f"Positie aangepast: "
                f"{original} -> {replacement}"
            )

            text = text.replace(
                original,
                replacement
            )
        else:
            print(
                f"Waarschuwing: positie niet gevonden: {original}"
            )
    text = text.replace(
        "^FO15,592",
        "^FO15,600"
    )

    text = text.replace(
        "^FO15,612",
        "^FO15,628"
    )

    text = text.replace(
        "^FO207,880^A0N,16,8",
        "^FO207,880^A0N,18,9"
    )

    return text


def modify_zpl(data):
    """
    Past één complete ZPL-printjob aan.
    """

    text = data.decode(
        "latin-1",
        errors="replace"
    )

    # Eerst alleen normale fonts aanpassen.
    # FWR-secties blijven volledig ongemoeid.
    text = adjust_fonts_by_orientation(text)

    # Daarna de specifieke veldposities aanpassen.
    text = apply_position_corrections(text)

    #
    # Meer ruimte voor datumregel onder DE-DPD-0145
    #

    text = text.replace(
        "^FO207,880^A0N,18,9^FB385,1,4,C",
        "^FO207,880^A0N,18,9^FB999,1,0,L"
    )

    return text.encode(
        "latin-1",
        errors="replace"
    )


def receive_payload(client):
    """
    Leest een complete printjob van de DPD-app.
    """

    payload = bytearray()

    while True:
        chunk = client.recv(8192)

        if not chunk:
            break

        payload.extend(chunk)

    return bytes(payload)


def send_to_printer(payload):
    """
    Stuurt de aangepaste ZPL naar de DULA 222.
    """

    with socket.create_connection(
        (PRINTER_IP, PRINTER_PORT),
        timeout=10
    ) as printer:
        printer.sendall(payload)

        try:
            printer.shutdown(socket.SHUT_WR)
        except OSError:
            pass


def save_file(filename, payload):
    """
    Slaat een ZPL-printjob op.
    """

    with open(filename, "wb") as output_file:
        output_file.write(payload)

    print(f"Bestand opgeslagen: {filename}")


def save_debug_files(original_payload, modified_payload):
    """
    Slaat originele en aangepaste ZPL op met een unieke tijdstempel.
    """

    timestamp = datetime.datetime.now().strftime(
        "%Y%m%d-%H%M%S-%f"
    )

    original_filename = (
        f"/tmp/dula-original-{timestamp}.zpl"
    )

    modified_filename = (
        f"/tmp/dula-modified-{timestamp}.zpl"
    )

    save_file(
        original_filename,
        original_payload
    )

    save_file(
        modified_filename,
        modified_payload
    )


def show_test_output(original_payload, modified_payload):
    """
    Schrijft de testoutput naar bestanden en toont de aangepaste ZPL.
    """

    save_file(
        TEST_ORIGINAL_FILE,
        original_payload
    )

    save_file(
        TEST_MODIFIED_FILE,
        modified_payload
    )

    modified_text = modified_payload.decode(
        "latin-1",
        errors="replace"
    )

    print()
    print("=" * 80)
    print("TESTMODUS: AANGEPASTE ZPL")
    print("Onderstaande data zou naar de DULA worden gestuurd.")
    print("=" * 80)
    print(modified_text)
    print("=" * 80)
    print("EINDE AANGEPASTE ZPL")
    print("=" * 80)
    print()
    print("Er is niets naar de printer gestuurd.")
    print(f"Origineel:  {TEST_ORIGINAL_FILE}")
    print(f"Aangepast:  {TEST_MODIFIED_FILE}")


def handle_client(
    client,
    client_address,
    test_mode,
    debug_mode
):
    """
    Verwerkt één verbinding en één ZPL-printjob.
    """

    try:
        print()
        print(
            f"Verbinding ontvangen van "
            f"{client_address[0]}:{client_address[1]}"
        )

        original_payload = receive_payload(client)

        if not original_payload:
            print("Lege printjob ontvangen")
            return

        print(
            f"Ontvangen: {len(original_payload)} bytes"
        )

        modified_payload = modify_zpl(
            original_payload
        )

        if debug_mode:
            save_debug_files(
                original_payload,
                modified_payload
            )

        if test_mode:
            show_test_output(
                original_payload,
                modified_payload
            )
        else:
            send_to_printer(
                modified_payload
            )

            print(
                f"Verzonden naar printer: "
                f"{len(modified_payload)} bytes"
            )

    except Exception as error:
        print(
            f"Fout bij verwerken van de printjob "
            f"van {client_address}: {error}"
        )

    finally:
        try:
            client.close()
        except OSError:
            pass


def main():
    arguments = parse_arguments()

    server = socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM
    )

    server.setsockopt(
        socket.SOL_SOCKET,
        socket.SO_REUSEADDR,
        1
    )

    server.bind(
        (LISTEN_IP, LISTEN_PORT)
    )

    server.listen(10)

    print(
        f"ZPL-proxy luistert op "
        f"{LISTEN_IP}:{LISTEN_PORT}"
    )

    if arguments.test:
        print()
        print("*** TESTMODUS ACTIEF ***")
        print("Printjobs worden niet naar de DULA gestuurd.")
        print(f"Testoutput: {TEST_MODIFIED_FILE}")
    else:
        print(
            f"Doelprinter: "
            f"{PRINTER_IP}:{PRINTER_PORT}"
        )

    if arguments.debug:
        print("Debugopslag is actief.")

    try:
        while True:
            client, client_address = server.accept()

            thread = threading.Thread(
                target=handle_client,
                args=(
                    client,
                    client_address,
                    arguments.test,
                    arguments.debug
                ),
                daemon=True
            )

            thread.start()

    except KeyboardInterrupt:
        print()
        print("ZPL-proxy gestopt")

    finally:
        server.close()


if __name__ == "__main__":
    main()
