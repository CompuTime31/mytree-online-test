# Test en ligne entre le PC et le téléphone

## Conditions
1. Le PC et le téléphone doivent être connectés au même réseau Wi-Fi.
2. Lancez `run-windows.bat` sur le PC.
3. Sur le PC, ouvrez `http://localhost:8080`.

## Trouver l’adresse IP du PC
1. Appuyez sur `Windows + R`.
2. Tapez `cmd`, puis Entrée.
3. Exécutez `ipconfig`.
4. Repérez **Adresse IPv4**, par exemple `192.168.1.25`.

## Connexion depuis le téléphone
Dans Safari ou Chrome, ouvrez :

`http://192.168.1.25:8080`

Remplacez l’exemple par l’adresse IPv4 réelle du PC.

Compte bénévole de test :
- utilisateur : `benevole`
- mot de passe : `benevole123`

Compte administrateur sur le PC :
- utilisateur : `admin`
- mot de passe : `admin123`

## Si le téléphone ne se connecte pas
- Vérifiez que les deux appareils sont sur le même Wi-Fi.
- Autorisez Python ou Waitress dans le pare-feu Windows pour les réseaux privés.
- Vérifiez que le port 8080 écoute avec : `netstat -ano | findstr :8080`.
- Désactivez temporairement les données mobiles du téléphone pour éviter qu’il quitte le Wi-Fi.

## Scénario de test conseillé
1. Connectez l’administrateur sur le PC.
2. Connectez le bénévole sur le téléphone.
3. Depuis le téléphone, créez une plantation ou une intervention.
4. Depuis le PC, actualisez la liste correspondante et contrôlez l’apparition de la donnée.
5. Validez ou modifiez depuis l’administration.
6. Actualisez le téléphone et contrôlez le résultat.
