import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";
import { 
  MapPin, 
  Navigation, 
  CheckCircle, 
  XCircle, 
  Loader2,
  RefreshCw,
  User
} from "lucide-react";
import { 
  getUserLocation, 
  requestLocationPermission, 
  type Location,
  getStaticMapUrl
} from "@/lib/locationUtils";

interface LocationPermissionProps {
  onLocationGranted: (location: Location) => void;
  onLocationDenied: () => void;
  showMap?: boolean;
}

export default function LocationPermission({ 
  onLocationGranted, 
  onLocationDenied,
  showMap = true 
}: LocationPermissionProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [userLocation, setUserLocation] = useState<Location | null>(null);
  const [permissionStatus, setPermissionStatus] = useState<'idle' | 'requesting' | 'granted' | 'denied'>('idle');
  const { toast } = useToast();

  useEffect(() => {
    checkLocationPermission();
  }, []);

  const checkLocationPermission = async () => {
    setIsLoading(true);
    try {
      const hasPermission = await requestLocationPermission();
      if (hasPermission) {
        setPermissionStatus('granted');
        const location = await getUserLocation();
        setUserLocation(location);
        onLocationGranted(location);
      } else {
        setPermissionStatus('denied');
        onLocationDenied();
      }
    } catch (error) {
      console.error('Location permission error:', error);
      setPermissionStatus('denied');
      onLocationDenied();
      toast({
        title: "Location Access Required",
        description: "Please enable location access to find nearby service providers.",
        variant: "destructive"
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleRequestLocation = async () => {
    setPermissionStatus('requesting');
    setIsLoading(true);
    
    try {
      const location = await getUserLocation();
      setUserLocation(location);
      setPermissionStatus('granted');
      onLocationGranted(location);
      toast({
        title: "Location Access Granted",
        description: "We can now show you nearby service providers.",
      });
    } catch (error) {
      console.error('Location request error:', error);
      setPermissionStatus('denied');
      onLocationDenied();
      toast({
        title: "Location Access Denied",
        description: "Please enable location access in your browser settings to find nearby providers.",
        variant: "destructive"
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleRefreshLocation = async () => {
    setIsLoading(true);
    try {
      const location = await getUserLocation();
      setUserLocation(location);
      onLocationGranted(location);
      toast({
        title: "Location Updated",
        description: "Your location has been refreshed.",
      });
    } catch (error) {
      console.error('Location refresh error:', error);
      toast({
        title: "Location Update Failed",
        description: "Could not update your location. Please try again.",
        variant: "destructive"
      });
    } finally {
      setIsLoading(false);
    }
  };

  if (isLoading && permissionStatus === 'idle') {
    return (
      <Card className="w-full max-w-md mx-auto">
        <CardContent className="p-6">
          <div className="flex items-center justify-center gap-3">
            <Loader2 className="h-6 w-6 animate-spin text-primary" />
            <span className="text-lg">Checking location access...</span>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (permissionStatus === 'granted' && userLocation) {
    return (
      <Card className="w-full max-w-md mx-auto">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <CheckCircle className="h-5 w-5 text-green-500" />
            Location Access Granted
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-2">
            <MapPin className="h-4 w-4 text-primary" />
            <span className="text-sm text-muted-foreground">
              {userLocation.address || `Lat: ${userLocation.latitude.toFixed(4)}, Lng: ${userLocation.longitude.toFixed(4)}`}
            </span>
          </div>
          
          {showMap && (
            <div className="space-y-2">
              <div className="h-48 rounded-lg overflow-hidden border">
                <img
                  src={getStaticMapUrl(userLocation.latitude, userLocation.longitude, 15, "400x200")}
                  alt="Your location"
                  className="w-full h-full object-cover"
                />
              </div>
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <User className="h-3 w-3" />
                <span>You are here</span>
              </div>
            </div>
          )}
          
          <Button 
            onClick={handleRefreshLocation} 
            variant="outline" 
            size="sm"
            disabled={isLoading}
            className="w-full"
          >
            {isLoading ? (
              <Loader2 className="h-4 w-4 animate-spin mr-2" />
            ) : (
              <RefreshCw className="h-4 w-4 mr-2" />
            )}
            Refresh Location
          </Button>
        </CardContent>
      </Card>
    );
  }

  if (permissionStatus === 'denied') {
    return (
      <Card className="w-full max-w-md mx-auto">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <XCircle className="h-5 w-5 text-red-500" />
            Location Access Required
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            To find nearby service providers, we need access to your location. 
            This helps us show you the closest available professionals.
          </p>
          
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-sm">
              <Navigation className="h-4 w-4 text-primary" />
              <span>Find nearby providers</span>
            </div>
            <div className="flex items-center gap-2 text-sm">
              <MapPin className="h-4 w-4 text-primary" />
              <span>See distance from your location</span>
            </div>
            <div className="flex items-center gap-2 text-sm">
              <CheckCircle className="h-4 w-4 text-primary" />
              <span>Get accurate service area information</span>
            </div>
          </div>
          
          <Button 
            onClick={handleRequestLocation} 
            disabled={isLoading}
            className="w-full"
          >
            {isLoading ? (
              <Loader2 className="h-4 w-4 animate-spin mr-2" />
            ) : (
              <MapPin className="h-4 w-4 mr-2" />
            )}
            Enable Location Access
          </Button>
          
          <p className="text-xs text-muted-foreground text-center">
            You can also manually enter your location in the search bar below
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="w-full max-w-md mx-auto">
      <CardContent className="p-6">
        <div className="flex items-center justify-center gap-3">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
          <span className="text-lg">Requesting location access...</span>
        </div>
      </CardContent>
    </Card>
  );
} 